#!/usr/bin/env python3
"""
Schedule PNG Renderer - авторський дизайн (1 або 2 дні на одну групу)
Генерує PNG тільки якщо дані змінилися (за хешем) АБО якщо змінилася дата
Хеші та дати зберігаються в папці hash/
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
    from matplotlib.patches import Rectangle, FancyBboxPatch, Polygon, Circle
except ImportError:
    print("ERROR: pip install matplotlib")
    sys.exit(1)

TEMPLATE_VERSION = "v10-dynamic-rows"

# Авторська палітра кольорів
BG_COLOR = '#FAF9F6'          # Теплий світлий фон полотна
HEADER_BG = '#1E293B'         # Глибокий графітово-синій фон шапки
HEADER_TEXT = '#F8FAFC'       # Світлий текст у шапці
LEFT_COL_BG = '#F1F5F9'       # Світло-сланцевий фон колонки дат
CELL_WHITE = '#FFFFFF'        # Світло є
CELL_OUTAGE = '#F7C6BC'       # Насичений теракотово-кораловий фон відключення
BORDER_COLOR = '#CBD5E1'      # Чіткі лінії сітки
HEADER_BORDER = '#334155'     # Лінії розділення годин у темній шапці
OUTER_BORDER = '#94A3B8'      # Зовнішній контур таблиці
TEXT_DARK = '#0F172A'         # Основний темний текст
TEXT_MUTED = '#64748B'        # Приглушений текст для дати отримання

BADGE_BG = '#FEF3C7'          # Теплий бурштиновий фон бейджа
BADGE_BORDER = '#F59E0B'      # Янтарна рамка бейджа
BADGE_DOT = '#D97706'         # Акцентна крапка в бейджі

# Контрастні кольори блискавки
BOLT_OFF = '#1E293B'          # Темний графіт на кораловому фоні (світла нема)
BOLT_ON = '#B45309'           # Насичений темно-бурштиновий на білому фоні (світло є)

SLOTS = list(range(1, 25))
HOURS = [f'{i:02d}-{i+1:02d}' for i in range(24)]

# Таймзона Київ (UTC+2)
KYIV_TZ = timezone(timedelta(hours=2))


def format_gpv_filename(gpv_key):
    cleaned = gpv_key.replace('GPV', '').replace('.', '-').lstrip('-')
    return f"gpv-{cleaned}-emergency.png"


def format_hash_filename(gpv_key):
    cleaned = gpv_key.replace('GPV', '').replace('.', '-').lstrip('-')
    return f"gpv-{cleaned}-emergency.hash"


def format_group_label(gpv_key, sch_names):
    raw_name = sch_names.get(gpv_key, gpv_key)
    if 'Черга' in raw_name:
        return raw_name.replace('Черга', 'Група:').replace('::', ':')
    cleaned = gpv_key.replace('GPV', '').strip()
    return f"Група: {cleaned}"


def calculate_data_hash(today_data, tomorrow_data, gpv_key, has_tomorrow):
    data_str = json.dumps({
        'template': TEMPLATE_VERSION,
        'has_tomorrow': has_tomorrow,
        'today': today_data.get(gpv_key, {}),
        'tomorrow': tomorrow_data.get(gpv_key, {}) if has_tomorrow else {}
    }, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(data_str.encode()).hexdigest()


def load_previous_hash(hash_dir, gpv_key):
    hash_file = hash_dir / format_hash_filename(gpv_key)
    if hash_file.exists():
        try:
            return hash_file.read_text(encoding='utf-8').strip()
        except Exception as e:
            print(f"[WARN] Could not read hash file {hash_file}: {e}")
    return None


def load_previous_date(hash_dir, gpv_key):
    date_file = hash_dir / format_hash_filename(gpv_key).replace('.hash', '.date')
    if date_file.exists():
        try:
            return date_file.read_text(encoding='utf-8').strip()
        except Exception as e:
            print(f"[WARN] Could not read date file {date_file}: {e}")
    return None


def save_hash(hash_dir, gpv_key, data_hash):
    hash_dir.mkdir(parents=True, exist_ok=True)
    hash_file = hash_dir / format_hash_filename(gpv_key)
    try:
        hash_file.write_text(data_hash, encoding='utf-8')
    except Exception as e:
        print(f"[WARN] Could not save hash file {hash_file}: {e}")


def save_date(hash_dir, gpv_key, date_str):
    hash_dir.mkdir(parents=True, exist_ok=True)
    date_file = hash_dir / format_hash_filename(gpv_key).replace('.hash', '.date')
    try:
        date_file.write_text(date_str, encoding='utf-8')
    except Exception as e:
        print(f"[WARN] Could not save date file {date_file}: {e}")


def draw_outage_icon(ax, cx, cy, size, state, zorder=5):
    """Малює збільшену контрастну перекреслену блискавку"""
    bolt_pts = [
        (0.06, -0.45),
        (-0.29, 0.04),
        (-0.03, 0.04),
        (-0.10, 0.45),
        (0.29, -0.04),
        (0.03, -0.04),
    ]
    scaled_bolt = [(cx + px * size, cy + py * size) for px, py in bolt_pts]

    d = 0.39 * size
    line_p1 = (cx - d, cy - d)
    line_p2 = (cx + d, cy + d)
    lw = 2.0

    if state == 'no':
        poly = Polygon(scaled_bolt, closed=True, facecolor=BOLT_OFF, edgecolor='none', zorder=zorder)
        ax.add_patch(poly)
        ax.plot([line_p1[0], line_p2[0]], [line_p1[1], line_p2[1]],
                color=BOLT_OFF, linewidth=lw, solid_capstyle='round', zorder=zorder + 1)

    elif state in ('first', 'second'):
        left_color = BOLT_OFF if state == 'first' else BOLT_ON
        right_color = BOLT_ON if state == 'first' else BOLT_OFF

        clip_left = Rectangle((cx - size * 2, cy - size * 2), size * 2, size * 4, facecolor='none', edgecolor='none')
        clip_right = Rectangle((cx, cy - size * 2), size * 2, size * 4, facecolor='none', edgecolor='none')
        ax.add_patch(clip_left)
        ax.add_patch(clip_right)

        poly_l = Polygon(scaled_bolt, closed=True, facecolor=left_color, edgecolor='none', zorder=zorder)
        ax.add_patch(poly_l)
        poly_l.set_clip_path(clip_left)

        line_l, = ax.plot([line_p1[0], line_p2[0]], [line_p1[1], line_p2[1]],
                          color=left_color, linewidth=lw, solid_capstyle='round', zorder=zorder + 1)
        line_l.set_clip_path(clip_left)

        poly_r = Polygon(scaled_bolt, closed=True, facecolor=right_color, edgecolor='none', zorder=zorder)
        ax.add_patch(poly_r)
        poly_r.set_clip_path(clip_right)

        line_r, = ax.plot([line_p1[0], line_p2[0]], [line_p1[1], line_p2[1]],
                          color=right_color, linewidth=lw, solid_capstyle='round', zorder=zorder + 1)
        line_r.set_clip_path(clip_right)


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

    today_str = f'{today_date.day:02d} {months_uk[today_date.month]}'
    tomorrow_str = f'{tomorrow_date.day:02d} {months_uk[tomorrow_date.month]}'
    today_date_code = today_date.strftime('%Y-%m-%d')
    fetched_time_str = datetime.now(KYIV_TZ).strftime('%d.%m.%Y %H:%M')

    gpv_keys = [gpv_key] if gpv_key else sorted([k for k in today_data if k.startswith('GPV')])

    if out_path:
        out_p = Path(out_path)
        out_p.mkdir(parents=True, exist_ok=True)
        hash_dir = out_p / 'hash'
    else:
        out_p = Path('.')
        hash_dir = out_p / 'hash'

    stats = {'checked': 0, 'skipped': 0, 'generated': 0}

    plt.rcParams['font.sans-serif'] = ['DejaVu Sans', 'Arial', 'Liberation Sans']
    plt.rcParams['axes.unicode_minus'] = False

    for gkey in gpv_keys:
        stats['checked'] += 1

        today_slots = today_data.get(gkey, {str(i): 'yes' for i in range(1, 25)})
        # Перевіряємо, чи є реальні дані на завтра для цієї групи
        raw_tomorrow = tomorrow_data.get(gkey)
        has_tomorrow = isinstance(raw_tomorrow, dict) and len(raw_tomorrow) > 0
        tomorrow_slots = raw_tomorrow if has_tomorrow else {}

        group_label = format_group_label(gkey, sch_names)

        filename = format_gpv_filename(gkey)
        output_file = out_p / filename

        new_hash = calculate_data_hash(today_data, tomorrow_data, gkey, has_tomorrow)
        prev_hash = load_previous_hash(hash_dir, gkey)
        prev_date = load_previous_date(hash_dir, gkey)

        date_changed = (prev_date != today_date_code)
        hash_changed = (new_hash != prev_hash)

        if not output_file.exists():
            print(f"[REGEN] {filename} (file not found)")
            regenerate = True
        elif hash_changed:
            print(f"[REGEN] {filename} (hash changed)")
            regenerate = True
        elif date_changed:
            print(f"[REGEN] {filename} (date changed: {prev_date} → {today_date_code})")
            regenerate = True
        else:
            print(f"[SKIP] {filename} (no changes)")
            stats['skipped'] += 1
            regenerate = False

        if not regenerate:
            continue

        stats['generated'] += 1

        # Кількість рядків: 2 якщо є графік на завтра, 1 якщо тільки на сьогодні
        num_rows = 2 if has_tomorrow else 1

        label_w = 3.65
        cell_w = 1.0
        header_h = 1.55
        row_h = 1.08
        table_w = label_w + 24 * cell_w
        table_h = header_h + num_rows * row_h

        top_margin = 1.35
        bottom_margin = 1.55
        side_margin = 0.7

        total_w = table_w + 2 * side_margin
        total_h = table_h + top_margin + bottom_margin

        # Пропорційна висота фігури залежно від кількості рядків (1 або 2)
        fig_height = 5.2 if num_rows == 2 else 4.35
        fig, ax = plt.subplots(figsize=(15.8, fig_height), dpi=150)
        fig.patch.set_facecolor(BG_COLOR)
        ax.set_facecolor(BG_COLOR)
        ax.set_xlim(0, total_w)
        ax.set_ylim(0, total_h)
        ax.invert_yaxis()
        ax.set_aspect('equal')
        ax.axis('off')

        tx = side_margin
        ty = top_margin

        # === 1. ВЕРХНІЙ БЛОК: ЗАГОЛОВОК І БЕЙДЖ ===
        accent_bar = FancyBboxPatch(
            (tx, 0.34), 0.14, 0.64,
            boxstyle="round,pad=0,rounding_size=0.07",
            facecolor=BADGE_BORDER, edgecolor='none', zorder=3
        )
        ax.add_patch(accent_bar)

        ax.text(tx + 0.34, 0.66, 'Графік відключень · Вінницька область',
                fontsize=18.5, fontweight='bold', color=TEXT_DARK, va='center', ha='left')

        badge_w = 4.35
        badge_h = 0.84
        badge_x = tx + table_w - badge_w
        badge_y = 0.24
        badge = FancyBboxPatch(
            (badge_x, badge_y), badge_w, badge_h,
            boxstyle="round,pad=0,rounding_size=0.22",
            facecolor=BADGE_BG, edgecolor=BADGE_BORDER, linewidth=1.3, zorder=3
        )
        ax.add_patch(badge)

        dot = Circle((badge_x + 0.52, badge_y + badge_h / 2), radius=0.12,
                     facecolor=BADGE_DOT, edgecolor='none', zorder=4)
        ax.add_patch(dot)

        ax.text(badge_x + badge_w / 2 + 0.15, badge_y + badge_h / 2, group_label,
                fontsize=15.0, fontweight='bold', color=TEXT_DARK, va='center', ha='center', zorder=4)

        # === 2. ТАБЛИЦЯ ІЗ ТЕМНОЮ ШАПКОЮ ===
        corner_r = 0.26
        table_clip = FancyBboxPatch(
            (tx, ty), table_w, table_h,
            boxstyle=f"round,pad=0,rounding_size={corner_r}",
            facecolor='none', edgecolor='none'
        )
        ax.add_patch(table_clip)

        hdr_bg = Rectangle((tx, ty), table_w, header_h, facecolor=HEADER_BG, edgecolor='none', zorder=1)
        ax.add_patch(hdr_bg)
        hdr_bg.set_clip_path(table_clip)

        left_col_bg = Rectangle((tx, ty + header_h), label_w, num_rows * row_h, facecolor=LEFT_COL_BG, edgecolor='none', zorder=1)
        ax.add_patch(left_col_bg)
        left_col_bg.set_clip_path(table_clip)

        ax.text(tx + 0.35, ty + header_h / 2, 'Часові\nпроміжки',
                fontsize=10.5, fontweight='bold', color=HEADER_TEXT, va='center', ha='left', linespacing=1.25, zorder=4)

        for i, h_label in enumerate(HOURS):
            cx = tx + label_w + i * cell_w + cell_w / 2
            cy = ty + header_h / 2
            ax.text(cx, cy, h_label,
                    fontsize=9.5, fontweight='bold', color=HEADER_TEXT,
                    va='center', ha='center', rotation=-90, zorder=4)

        def render_day_row(row_idx, date_label, slots_dict):
            ry = ty + header_h + row_idx * row_h

            ax.text(tx + 0.35, ry + row_h / 2, date_label,
                    fontsize=10.2, fontweight='bold', color=TEXT_DARK, va='center', ha='left', zorder=4)

            for i, slot_num in enumerate(SLOTS):
                sx = tx + label_w + i * cell_w
                state = slots_dict.get(str(slot_num), 'yes')

                base_rect = Rectangle((sx, ry), cell_w, row_h, facecolor=CELL_WHITE, edgecolor='none', zorder=1)
                ax.add_patch(base_rect)
                base_rect.set_clip_path(table_clip)

                if state == 'no':
                    fill = Rectangle((sx, ry), cell_w, row_h, facecolor=CELL_OUTAGE, edgecolor='none', zorder=2)
                    ax.add_patch(fill)
                    fill.set_clip_path(table_clip)
                elif state == 'first':
                    fill = Rectangle((sx, ry), cell_w / 2, row_h, facecolor=CELL_OUTAGE, edgecolor='none', zorder=2)
                    ax.add_patch(fill)
                    fill.set_clip_path(table_clip)
                elif state == 'second':
                    fill = Rectangle((sx + cell_w / 2, ry), cell_w / 2, row_h, facecolor=CELL_OUTAGE, edgecolor='none', zorder=2)
                    ax.add_patch(fill)
                    fill.set_clip_path(table_clip)

                if state in ('no', 'first', 'second'):
                    draw_outage_icon(ax, sx + cell_w / 2, ry + row_h / 2, size=0.72, state=state, zorder=5)

        render_day_row(0, today_str, today_slots)
        if has_tomorrow:
            render_day_row(1, tomorrow_str, tomorrow_slots)

        # Горизонтальна лінія між рядками малюється тільки якщо рядків два
        if has_tomorrow:
            line_mid, = ax.plot([tx, tx + table_w], [ty + header_h + row_h, ty + header_h + row_h],
                                color=BORDER_COLOR, linewidth=0.9, zorder=3)
            line_mid.set_clip_path(table_clip)

        for i in range(24):
            vx = tx + label_w + i * cell_w
            l_top, = ax.plot([vx, vx], [ty, ty + header_h], color=HEADER_BORDER, linewidth=0.7, zorder=3)
            l_top.set_clip_path(table_clip)

            l_bot, = ax.plot([vx, vx], [ty + header_h, ty + table_h], color=BORDER_COLOR, linewidth=0.8, zorder=3)
            l_bot.set_clip_path(table_clip)

        outer_box = FancyBboxPatch(
            (tx, ty), table_w, table_h,
            boxstyle=f"round,pad=0,rounding_size={corner_r}",
            facecolor='none', edgecolor=OUTER_BORDER, linewidth=1.1, zorder=6
        )
        ax.add_patch(outer_box)

        # === 3. НИЖНІЙ БЛОК: ЛЕГЕНДА ТА "ДАНІ ОТРИМАНО" ===
        leg_y = ty + table_h + 0.42
        box_size = 0.78

        legend_items = [
            ('yes', 'Світло є'),
            ('no', 'Світла нема'),
            ('first', 'Перші 30 хв.'),
            ('second', 'Другі 30 хв.'),
        ]

        curr_x = tx
        for state, text_lbl in legend_items:
            b_rect = Rectangle((curr_x, leg_y), box_size, box_size,
                               facecolor=CELL_WHITE, edgecolor=OUTER_BORDER, linewidth=0.9, zorder=2)
            ax.add_patch(b_rect)

            if state == 'no':
                f_rect = Rectangle((curr_x, leg_y), box_size, box_size,
                                   facecolor=CELL_OUTAGE, edgecolor='none', zorder=3)
                ax.add_patch(f_rect)
            elif state == 'first':
                f_rect = Rectangle((curr_x, leg_y), box_size / 2, box_size,
                                   facecolor=CELL_OUTAGE, edgecolor='none', zorder=3)
                ax.add_patch(f_rect)
            elif state == 'second':
                f_rect = Rectangle((curr_x + box_size / 2, leg_y), box_size / 2, box_size,
                                   facecolor=CELL_OUTAGE, edgecolor='none', zorder=3)
                ax.add_patch(f_rect)

            border_rect = Rectangle((curr_x, leg_y), box_size, box_size,
                                    facecolor='none', edgecolor=OUTER_BORDER, linewidth=0.9, zorder=4)
            ax.add_patch(border_rect)

            if state != 'yes':
                draw_outage_icon(ax, curr_x + box_size / 2, leg_y + box_size / 2, size=0.54, state=state, zorder=5)

            ax.text(curr_x + box_size + 0.28, leg_y + box_size / 2, text_lbl,
                    fontsize=9.8, color=TEXT_DARK, va='center', ha='left')

            curr_x += 3.55

        display_time = last_updated if last_updated else fetched_time_str
        ax.text(tx + table_w, leg_y + box_size / 2, f'Дані отримано: {display_time}',
                fontsize=10.0, color=TEXT_MUTED, style='italic', va='center', ha='right')

        plt.savefig(output_file, facecolor=BG_COLOR, dpi=150, bbox_inches='tight', pad_inches=0.18)
        print(f"[OK] {output_file}")

        save_hash(hash_dir, gkey, new_hash)
        save_date(hash_dir, gkey, today_date_code)

        plt.close(fig)

    print(f"\n[STATS] Checked: {stats['checked']}, Generated: {stats['generated']}, Skipped: {stats['skipped']}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--json', required=True)
    parser.add_argument('--gpv', default=None)
    parser.add_argument('--out', default=None)
    args = parser.parse_args()

    render_schedule(args.json, args.gpv, args.out)
