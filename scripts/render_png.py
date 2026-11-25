#!/usr/bin/env python3
"""
Schedule PNG Renderer - мобільна сітка 6x4 (1 або 2 дні поруч)
Рахує зміни відносно ОСТАННЬОГО опублікованого графіка на цю дату:
- Червона рамка: додалося відключення ("Більше відключень")
- Зелена рамка: скасовано/зменшено відключення ("Менше відключень")
"""

import json
import argparse
from pathlib import Path
import sys
from datetime import datetime, timezone, timedelta
import hashlib

try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle, FancyBboxPatch, Circle
except ImportError:
    print("ERROR: pip install matplotlib")
    sys.exit(1)

TEMPLATE_VERSION = "v16-mobile-cards-last-diff"

# Палітра кольорів
BG_COLOR = '#FAF9F6'          # Теплий світлий фон полотна
HEADER_BG = '#1E293B'         # Графітово-синій фон заголовка дня
HEADER_TEXT = '#F8FAFC'       # Світлий текст у заголовку
CELL_WHITE = '#FFFFFF'        # Світло є
CELL_OUTAGE = '#F7C6BC'       # Теракотово-кораловий фон відключення
BORDER_COLOR = '#94A3B8'      # Чіткі внутрішні лінії сітки
HALF_BORDER = '#CBD5E1'       # Тонка межа всередині 30-хв клітинки
OUTER_BORDER = '#475569'      # Контрастний зовнішній контур картки
TEXT_DARK = '#0F172A'         # Основний темний текст (години відключень)
TEXT_MUTED = '#64748B'        # Приглушений текст (години зі світлом та футер)

# Кольори індикації змін
DIFF_MORE_BORDER = '#DC2626'  # Червоний: більше відключень
DIFF_LESS_BORDER = '#16A34A'  # Зелений: менше відключень

BADGE_BG = '#FEF3C7'          # Фон бейджа групи
BADGE_BORDER = '#F59E0B'      # Рамка бейджа
BADGE_DOT = '#D97706'         # Крапка в бейджі

KYIV_TZ = timezone(timedelta(hours=2))


def format_gpv_filename(gpv_key):
    cleaned = gpv_key.replace('GPV', '').replace('.', '-').lstrip('-')
    return f"gpv-{cleaned}-emergency.png"


def format_hash_filename(gpv_key):
    cleaned = gpv_key.replace('GPV', '').replace('.', '-').lstrip('-')
    return f"gpv-{cleaned}-emergency.hash"


def format_state_filename(gpv_key):
    cleaned = gpv_key.replace('GPV', '').replace('.', '-').lstrip('-')
    return f"gpv-{cleaned}-emergency.state.json"


def format_group_label(gpv_key, sch_names):
    raw_name = sch_names.get(gpv_key, gpv_key)
    if 'Черга' in raw_name:
        return raw_name.replace('Черга', 'Група:').replace('::', ':')
    cleaned = gpv_key.replace('GPV', '').strip()
    return f"Група: {cleaned}"


def load_text_file(path):
    if path.exists():
        try:
            return path.read_text(encoding='utf-8').strip()
        except Exception as e:
            print(f"[WARN] Could not read {path}: {e}")
    return None


def save_text_file(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.write_text(content, encoding='utf-8')
    except Exception as e:
        print(f"[WARN] Could not save {path}: {e}")


def load_last_state(state_path):
    if state_path.exists():
        try:
            return json.loads(state_path.read_text(encoding='utf-8'))
        except Exception as e:
            print(f"[WARN] Could not read state file {state_path}: {e}")
    return {}


def save_last_state(state_path, state_data):
    state_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        state_path.write_text(
            json.dumps(state_data, ensure_ascii=False, indent=2, sort_keys=True),
            encoding='utf-8'
        )
    except Exception as e:
        print(f"[WARN] Could not save state file {state_path}: {e}")


def outage_minutes(state):
    if state == 'no':
        return 60
    if state in ('first', 'second'):
        return 30
    return 0


def compute_slot_diffs(current_slots, previous_slots):
    """
    Повертає словник {'1': 'more' | 'less', ...}
    відносно попереднього опублікованого графіка на цю дату.
    """
    if not previous_slots:
        return {}

    diffs = {}
    for i in range(1, 25):
        key = str(i)
        cur = current_slots.get(key, 'yes')
        prev = previous_slots.get(key, 'yes')

        if cur == prev:
            continue

        cur_min = outage_minutes(cur)
        prev_min = outage_minutes(prev)

        if cur_min > prev_min:
            diffs[key] = 'more'
        elif cur_min < prev_min:
            diffs[key] = 'less'
        else:
            diffs[key] = 'more'

    return diffs


def calculate_data_hash(today_slots, tomorrow_slots, today_diffs, tomorrow_diffs, has_tomorrow):
    data_str = json.dumps({
        'template': TEMPLATE_VERSION,
        'has_tomorrow': has_tomorrow,
        'today': today_slots,
        'tomorrow': tomorrow_slots if has_tomorrow else {},
        'today_diffs': today_diffs,
        'tomorrow_diffs': tomorrow_diffs if has_tomorrow else {}
    }, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(data_str.encode()).hexdigest()


def draw_day_card(ax, cx, cy, card_w, day_title, slots_dict, diffs_dict):
    """Малює одну картку дня: шапка з датою + сітка 4 стовпці x 6 рядків + рамки змін"""
    cols = 4
    rows = 6
    hdr_h = 0.82
    cell_w = card_w / cols
    cell_h = 0.88
    card_h = hdr_h + rows * cell_h
    corner_r = 0.22

    card_clip = FancyBboxPatch(
        (cx, cy), card_w, card_h,
        boxstyle=f"round,pad=0,rounding_size={corner_r}",
        facecolor='none', edgecolor='none'
    )
    ax.add_patch(card_clip)

    # Шапка картки (Дата / день)
    hdr_rect = Rectangle((cx, cy), card_w, hdr_h, facecolor=HEADER_BG, edgecolor='none', zorder=1)
    ax.add_patch(hdr_rect)
    hdr_rect.set_clip_path(card_clip)

    ax.text(cx + card_w / 2, cy + hdr_h / 2, day_title,
            fontsize=13.5, fontweight='bold', color=HEADER_TEXT, va='center', ha='center', zorder=4)

    # Клітинки 00 - 01 .. 23 - 24
    for slot_idx in range(24):
        r = slot_idx // cols
        c = slot_idx % cols
        sx = cx + c * cell_w
        sy = cy + hdr_h + r * cell_h

        slot_key = str(slot_idx + 1)
        state = slots_dict.get(slot_key, 'yes')
        hour_label = f"{slot_idx:02d} - {slot_idx + 1:02d}"

        # Базовий білий фон
        base = Rectangle((sx, sy), cell_w, cell_h, facecolor=CELL_WHITE, edgecolor='none', zorder=1)
        ax.add_patch(base)
        base.set_clip_path(card_clip)

        # Заливка відключення
        if state == 'no':
            fill = Rectangle((sx, sy), cell_w, cell_h, facecolor=CELL_OUTAGE, edgecolor='none', zorder=2)
            ax.add_patch(fill)
            fill.set_clip_path(card_clip)
        elif state == 'first':
            fill = Rectangle((sx, sy), cell_w / 2, cell_h, facecolor=CELL_OUTAGE, edgecolor='none', zorder=2)
            ax.add_patch(fill)
            fill.set_clip_path(card_clip)
            mid_line, = ax.plot([sx + cell_w / 2, sx + cell_w / 2], [sy, sy + cell_h],
                                color=HALF_BORDER, linewidth=0.8, linestyle='--', zorder=2.5)
            mid_line.set_clip_path(card_clip)
        elif state == 'second':
            fill = Rectangle((sx + cell_w / 2, sy), cell_w / 2, cell_h, facecolor=CELL_OUTAGE, edgecolor='none', zorder=2)
            ax.add_patch(fill)
            fill.set_clip_path(card_clip)
            mid_line, = ax.plot([sx + cell_w / 2, sx + cell_w / 2], [sy, sy + cell_h],
                                color=HALF_BORDER, linewidth=0.8, linestyle='--', zorder=2.5)
            mid_line.set_clip_path(card_clip)

        # Текст інтервалу всередині клітинки
        is_outage = state in ('no', 'first', 'second')
        txt_color = TEXT_DARK if is_outage else TEXT_MUTED
        txt_weight = 'bold' if is_outage else 'medium'

        ax.text(sx + cell_w / 2, sy + cell_h / 2, hour_label,
                fontsize=12.0, fontweight=txt_weight, color=txt_color,
                va='center', ha='center', zorder=5)

    # Чітка межа між шапкою та сіткою
    hdr_border, = ax.plot([cx, cx + card_w], [cy + hdr_h, cy + hdr_h],
                          color=OUTER_BORDER, linewidth=1.3, zorder=3.5)
    hdr_border.set_clip_path(card_clip)

    # Внутрішні горизонтальні лінії
    for r in range(1, rows):
        ly = cy + hdr_h + r * cell_h
        line, = ax.plot([cx, cx + card_w], [ly, ly], color=BORDER_COLOR, linewidth=1.25, zorder=3)
        line.set_clip_path(card_clip)

    # Внутрішні вертикальні лінії
    for c in range(1, cols):
        lx = cx + c * cell_w
        line, = ax.plot([lx, lx], [cy + hdr_h, cy + card_h], color=BORDER_COLOR, linewidth=1.25, zorder=3)
        line.set_clip_path(card_clip)

    # Кольорові рамки змін поверх сітки (червона — більше відключень, зелена — менше)
    pad = 0.032
    for slot_idx in range(24):
        slot_key = str(slot_idx + 1)
        diff_type = diffs_dict.get(slot_key)
        if not diff_type:
            continue

        r = slot_idx // cols
        c = slot_idx % cols
        sx = cx + c * cell_w
        sy = cy + hdr_h + r * cell_h

        diff_color = DIFF_MORE_BORDER if diff_type == 'more' else DIFF_LESS_BORDER
        diff_rect = Rectangle(
            (sx + pad, sy + pad),
            cell_w - 2 * pad,
            cell_h - 2 * pad,
            facecolor='none',
            edgecolor=diff_color,
            linewidth=2.3,
            zorder=5.5
        )
        ax.add_patch(diff_rect)
        diff_rect.set_clip_path(card_clip)

    # Контрастний зовнішній контур картки
    outer = FancyBboxPatch(
        (cx, cy), card_w, card_h,
        boxstyle=f"round,pad=0,rounding_size={corner_r}",
        facecolor='none', edgecolor=OUTER_BORDER, linewidth=1.6, zorder=6
    )
    ax.add_patch(outer)
    return card_h


def render_schedule(json_path, gpv_key=None, out_path=None):
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    fact_data = data.get('fact', {}).get('data', {})
    sch_names = data.get('preset', {}).get('sch_names', {})
    last_updated = data.get('fact', {}).get('update', '')
    today_ts = str(data.get('fact', {}).get('today'))
    tomorrow_ts = str(int(today_ts) + 86400)

    today_data = fact_data.get(today_ts, {})
    tomorrow_data = fact_data.get(tomorrow_ts, {})

    today_date = datetime.fromtimestamp(int(today_ts), tz=KYIV_TZ)
    tomorrow_date = datetime.fromtimestamp(int(tomorrow_ts), tz=KYIV_TZ)

    months_uk = {
        1: 'січня', 2: 'лютого', 3: 'березня', 4: 'квітня',
        5: 'травня', 6: 'червня', 7: 'липня', 8: 'серпня',
        9: 'вересня', 10: 'жовтня', 11: 'листопада', 12: 'грудня'
    }

    today_title = f"Сьогодні · {today_date.day:02d} {months_uk[today_date.month]}"
    tomorrow_title = f"Завтра · {tomorrow_date.day:02d} {months_uk[tomorrow_date.month]}"
    today_date_code = today_date.strftime('%Y-%m-%d')
    tomorrow_date_code = tomorrow_date.strftime('%Y-%m-%d')
    fetched_time_str = datetime.now(KYIV_TZ).strftime('%d.%m.%Y %H:%M')

    gpv_keys = [gpv_key] if gpv_key else sorted([k for k in today_data if k.startswith('GPV')])

    out_p = Path(out_path) if out_path else Path('.')
    out_p.mkdir(parents=True, exist_ok=True)
    hash_dir = out_p / 'hash'

    stats = {'checked': 0, 'skipped': 0, 'generated': 0}

    plt.rcParams['font.sans-serif'] = ['DejaVu Sans', 'Arial', 'Liberation Sans']
    plt.rcParams['axes.unicode_minus'] = False

    for gkey in gpv_keys:
        stats['checked'] += 1

        today_slots = today_data.get(gkey, {str(i): 'yes' for i in range(1, 25)})
        raw_tomorrow = tomorrow_data.get(gkey)

        has_tomorrow = (
            isinstance(raw_tomorrow, dict)
            and len(raw_tomorrow) > 0
            and any(v in ('no', 'first', 'second') for v in raw_tomorrow.values())
        )
        tomorrow_slots = raw_tomorrow if has_tomorrow else {}

        # Завантажуємо стан попередньої публікації: {'2026-11-25': {'slots': {...}, 'diffs': {...}}}
        state_file = hash_dir / format_state_filename(gkey)
        last_state = load_last_state(state_file)
        state_modified = False

        # Очищаємо застарілі дати
        valid_dates = {today_date_code, tomorrow_date_code}
        for old_date in list(last_state.keys()):
            if old_date not in valid_dates:
                del last_state[old_date]
                state_modified = True

        def resolve_day_state(date_code, cur_slots):
            nonlocal state_modified
            entry = last_state.get(date_code)
            # Міграція зі старого формату state.json, якщо там були просто слоти без 'slots'/'diffs'
            if isinstance(entry, dict) and 'slots' not in entry:
                entry = {'slots': entry, 'diffs': {}}

            if entry is None:
                # Перша публікація цієї дати — фіксуємо без рамок змін
                last_state[date_code] = {'slots': cur_slots, 'diffs': {}}
                state_modified = True
                return {}

            prev_slots = entry.get('slots', {})
            if cur_slots != prev_slots:
                # Графік оновився! Рахуємо різницю від ОСТАННЬОГО опублікованого і оновлюємо збережений стан
                new_diffs = compute_slot_diffs(cur_slots, prev_slots)
                last_state[date_code] = {'slots': cur_slots, 'diffs': new_diffs}
                state_modified = True
                return new_diffs

            # Графік не змінювався з моменту останнього оновлення — зберігаємо поточні рамки змін
            return entry.get('diffs', {})

        today_diffs = resolve_day_state(today_date_code, today_slots)
        if has_tomorrow:
            tomorrow_diffs = resolve_day_state(tomorrow_date_code, tomorrow_slots)
        else:
            tomorrow_diffs = {}
            if tomorrow_date_code in last_state:
                del last_state[tomorrow_date_code]
                state_modified = True

        if state_modified:
            save_last_state(state_file, last_state)

        has_any_diff = bool(today_diffs or tomorrow_diffs)

        group_label = format_group_label(gkey, sch_names)
        filename = format_gpv_filename(gkey)
        output_file = out_p / filename

        hash_file = hash_dir / format_hash_filename(gkey)
        date_file = hash_dir / format_hash_filename(gkey).replace('.hash', '.date')

        new_hash = calculate_data_hash(today_slots, tomorrow_slots, today_diffs, tomorrow_diffs, has_tomorrow)
        prev_hash = load_text_file(hash_file)
        prev_date = load_text_file(date_file)

        if not output_file.exists():
            print(f"[REGEN] {filename} (file not found)")
            regenerate = True
        elif new_hash != prev_hash:
            print(f"[REGEN] {filename} (hash/diffs changed)")
            regenerate = True
        elif prev_date != today_date_code:
            print(f"[REGEN] {filename} (date changed: {prev_date} → {today_date_code})")
            regenerate = True
        else:
            print(f"[SKIP] {filename} (no changes)")
            stats['skipped'] += 1
            regenerate = False

        if not regenerate:
            continue

        stats['generated'] += 1

        # Геометрія полотна залежно від кількості днів
        card_w = 6.8
        card_gap = 0.55 if has_tomorrow else 0.0
        num_cards = 2 if has_tomorrow else 1

        content_w = num_cards * card_w + card_gap
        side_margin = 0.55
        top_margin = 1.45
        bottom_margin = (1.95 if has_any_diff else 1.45) if has_tomorrow else (2.40 if has_any_diff else 1.85)

        card_h = 0.82 + 6 * 0.88
        total_w = content_w + 2 * side_margin
        total_h = top_margin + card_h + bottom_margin

        fig, ax = plt.subplots(figsize=(total_w, total_h), dpi=160)
        fig.patch.set_facecolor(BG_COLOR)
        ax.set_facecolor(BG_COLOR)
        ax.set_xlim(0, total_w)
        ax.set_ylim(0, total_h)
        ax.invert_yaxis()
        ax.set_aspect('equal')
        ax.axis('off')

        tx = side_margin

        # === 1. ВЕРХНІЙ БЛОК: ЗАГОЛОВОК І БЕЙДЖ ===
        accent_bar = FancyBboxPatch(
            (tx, 0.32), 0.14, 0.78,
            boxstyle="round,pad=0,rounding_size=0.07",
            facecolor=BADGE_BORDER, edgecolor='none', zorder=3
        )
        ax.add_patch(accent_bar)

        title_fs = 16.5 if has_tomorrow else 14.5
        ax.text(tx + 0.32, 0.52, 'Графік відключення',
                fontsize=title_fs, fontweight='bold', color=TEXT_DARK, va='center', ha='left', zorder=4)
        ax.text(tx + 0.32, 0.94, 'Вінницька область',
                fontsize=11.0, fontweight='medium', color=TEXT_MUTED, va='center', ha='left', zorder=4)

        badge_w = 3.15 if has_tomorrow else 2.75
        badge_h = 0.78
        badge_x = tx + content_w - badge_w
        badge_y = 0.32
        badge = FancyBboxPatch(
            (badge_x, badge_y), badge_w, badge_h,
            boxstyle="round,pad=0,rounding_size=0.20",
            facecolor=BADGE_BG, edgecolor=BADGE_BORDER, linewidth=1.4, zorder=3
        )
        ax.add_patch(badge)

        dot_offset = 0.40 if has_tomorrow else 0.34
        dot = Circle((badge_x + dot_offset, badge_y + badge_h / 2), radius=0.10,
                     facecolor=BADGE_DOT, edgecolor='none', zorder=4)
        ax.add_patch(dot)

        badge_fs = 13.5 if has_tomorrow else 12.5
        ax.text(badge_x + badge_w / 2 + 0.14, badge_y + badge_h / 2, group_label,
                fontsize=badge_fs, fontweight='bold', color=TEXT_DARK, va='center', ha='center', zorder=4)

        # === 2. КАРТКИ ДНІВ (1 АБО 2 ПОРУЧ) ===
        ty = top_margin
        draw_day_card(ax, tx, ty, card_w, today_title, today_slots, today_diffs)

        if has_tomorrow:
            draw_day_card(ax, tx + card_w + card_gap, ty, card_w, tomorrow_title, tomorrow_slots, tomorrow_diffs)

        # === 3. НИЖНІЙ БЛОК: ЛЕГЕНДА ТА ЧАС ОНОВЛЕННЯ ===
        leg_y = ty + card_h + 0.38
        box_w = 0.56
        box_h = 0.42

        base_legend = [
            ('yes', 'Світло є'),
            ('no', 'Немає'),
            ('first', 'Перші 30 хв'),
            ('second', 'Другі 30 хв'),
        ]

        diff_legend = [
            ('more', 'Більше відключень'),
            ('less', 'Менше відключень'),
        ]

        def draw_legend_box(lx, ly, kind):
            ax.add_patch(Rectangle((lx, ly), box_w, box_h,
                                   facecolor=CELL_WHITE, edgecolor='none', zorder=2))
            if kind == 'no':
                ax.add_patch(Rectangle((lx, ly), box_w, box_h,
                                       facecolor=CELL_OUTAGE, edgecolor='none', zorder=3))
            elif kind == 'first':
                ax.add_patch(Rectangle((lx, ly), box_w / 2, box_h,
                                       facecolor=CELL_OUTAGE, edgecolor='none', zorder=3))
            elif kind == 'second':
                ax.add_patch(Rectangle((lx + box_w / 2, ly), box_w / 2, box_h,
                                       facecolor=CELL_OUTAGE, edgecolor='none', zorder=3))

            if kind == 'more':
                ax.add_patch(Rectangle((lx, ly), box_w, box_h,
                                       facecolor='none', edgecolor=DIFF_MORE_BORDER, linewidth=2.1, zorder=4))
            elif kind == 'less':
                ax.add_patch(Rectangle((lx, ly), box_w, box_h,
                                       facecolor='none', edgecolor=DIFF_LESS_BORDER, linewidth=2.1, zorder=4))
            else:
                ax.add_patch(Rectangle((lx, ly), box_w, box_h,
                                       facecolor='none', edgecolor=OUTER_BORDER, linewidth=1.2, zorder=4))

        display_time = last_updated if last_updated else fetched_time_str

        if has_tomorrow:
            curr_x = tx
            step_x = 2.45
            for state, text_lbl in base_legend:
                draw_legend_box(curr_x, leg_y, state)
                ax.text(curr_x + box_w + 0.16, leg_y + box_h / 2, text_lbl,
                        fontsize=10.0, color=TEXT_DARK, va='center', ha='left')
                curr_x += step_x

            if has_any_diff:
                diff_y = leg_y + 0.56
                dx = tx
                for d_kind, d_lbl in diff_legend:
                    draw_legend_box(dx, diff_y, d_kind)
                    ax.text(dx + box_w + 0.16, diff_y + box_h / 2, d_lbl,
                            fontsize=10.0, color=TEXT_DARK, va='center', ha='left')
                    dx += 3.35
                ax.text(tx + content_w, diff_y + box_h / 2, f'Оновлено: {display_time}',
                        fontsize=9.5, color=TEXT_MUTED, style='italic', va='center', ha='right')
            else:
                ax.text(tx + content_w, leg_y + box_h / 2, f'Оновлено: {display_time}',
                        fontsize=9.5, color=TEXT_MUTED, style='italic', va='center', ha='right')
        else:
            col_step = 3.35
            row_step = 0.54
            for idx, (state, text_lbl) in enumerate(base_legend):
                lx = tx + (idx % 2) * col_step
                ly = leg_y + (idx // 2) * row_step
                draw_legend_box(lx, ly, state)
                ax.text(lx + box_w + 0.18, ly + box_h / 2, text_lbl,
                        fontsize=10.0, color=TEXT_DARK, va='center', ha='left')

            last_row_idx = 2
            if has_any_diff:
                for idx, (d_kind, d_lbl) in enumerate(diff_legend):
                    lx = tx + idx * col_step
                    ly = leg_y + 2 * row_step
                    draw_legend_box(lx, ly, d_kind)
                    ax.text(lx + box_w + 0.18, ly + box_h / 2, d_lbl,
                            fontsize=10.0, color=TEXT_DARK, va='center', ha='left')
                last_row_idx = 3

            ax.text(tx + content_w, leg_y + row_step * last_row_idx + 0.12, f'Дані отримано: {display_time}',
                    fontsize=9.5, color=TEXT_MUTED, style='italic', va='center', ha='right')

        plt.savefig(output_file, facecolor=BG_COLOR, dpi=160, bbox_inches='tight', pad_inches=0.18)
        print(f"[OK] {output_file}")

        save_text_file(hash_file, new_hash)
        save_text_file(date_file, today_date_code)
        plt.close(fig)

    print(f"\n[STATS] Checked: {stats['checked']}, Generated: {stats['generated']}, Skipped: {stats['skipped']}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--json', required=True)
    parser.add_argument('--gpv', default=None)
    parser.add_argument('--out', default=None)
    args = parser.parse_args()

    render_schedule(args.json, args.gpv, args.out)
