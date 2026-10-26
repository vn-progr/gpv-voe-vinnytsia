#!/usr/bin/env python3
"""
Schedule PNG Renderer - окремі таблиці (2 дні на одну чергу)
Генерує PNG тільки якщо дані змінилися (за хешем) АБО якщо змінилася дата
Хеші та дати зберігаються в папці hash/ 
Schedule PNG Renderer - Мобільно-адаптована версія для Telegram
Згенеровані PNG легко читаються як з ПК, так і з екранів смартфонів.
"""

import json
import argparse
from pathlib import Path
import sys
from datetime import datetime, timezone, timedelta
import hashlib

try:
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyBboxPatch, Rectangle
except ImportError:
    print("ERROR: pip install matplotlib")
    sys.exit(1)

# Палітра кольорів з високим контрастом
BG_COLOR = '#FFFFFF'
HEADER_BG = '#E2E8F0'
LABEL_BG = '#FEF3C7'
CELL_EMPTY = '#F1F5F9'
CELL_BORDER = '#94A3B8'
ORANGE = '#F95721'
TEXT_DARK = '#0F172A'

SLOTS = list(range(1, 25))
HOURS_TEXT = [f'{i:02d}-{i+1:02d}' for i in range(24)]

KYIV_TZ = timezone(timedelta(hours=2))

def format_gpv_filename(gpv_key):
    cleaned = gpv_key.replace('GPV', '').replace('.', '-').lstrip('-')
    return f"gpv-{cleaned}-emergency.png"

def format_hash_filename(gpv_key):
    cleaned = gpv_key.replace('GPV', '').replace('.', '-').lstrip('-')
    return f"gpv-{cleaned}-emergency.hash"

def calculate_data_hash(today_data, tomorrow_data, gpv_key):
    data_str = json.dumps({
        'today': today_data.get(gpv_key, {}),
        'tomorrow': tomorrow_data.get(gpv_key, {})
    }, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(data_str.encode()).hexdigest()

def load_previous_hash(hash_dir, gpv_key):
    hash_file = hash_dir / format_hash_filename(gpv_key)
    if hash_file.exists():
        try:
            with open(hash_file, 'r', encoding='utf-8') as f:
                return f.read().strip()
        except Exception:
            pass
    return None

def load_previous_date(hash_dir, gpv_key):
    date_file = hash_dir / format_hash_filename(gpv_key).replace('.hash', '.date')
    if date_file.exists():
        try:
            with open(date_file, 'r', encoding='utf-8') as f:
                return f.read().strip()
        except Exception:
            pass
    return None

def save_hash(hash_dir, gpv_key, data_hash):
    hash_dir.mkdir(parents=True, exist_ok=True)
    with open(hash_dir / format_hash_filename(gpv_key), 'w', encoding='utf-8') as f:
        f.write(data_hash)

def save_date(hash_dir, gpv_key, date_str):
    hash_dir.mkdir(parents=True, exist_ok=True)
    date_file = hash_dir / format_hash_filename(gpv_key).replace('.hash', '.date')
    with open(date_file, 'w', encoding='utf-8') as f:
        f.write(date_str)

def draw_rounded_slot(ax, x, y, width, height, state, r=0.15):
    """Малює клітинку із чіткою обводкою для мобільних екранів"""
    bg = FancyBboxPatch((x, y), width, height,
                        boxstyle=f"round,pad=0,rounding_size={r}",
                        facecolor=CELL_EMPTY, edgecolor=CELL_BORDER, linewidth=1.2)
    ax.add_patch(bg)

    if state == 'no':
        fill = FancyBboxPatch((x, y), width, height,
                              boxstyle=f"round,pad=0,rounding_size={r}",
                              facecolor=ORANGE, edgecolor='none')
        ax.add_patch(fill)

    elif state == 'first':
        fill = FancyBboxPatch((x, y), width, height,
                              boxstyle=f"round,pad=0,rounding_size={r}",
                              facecolor=ORANGE, edgecolor='none')
        ax.add_patch(fill)
        clip_right = Rectangle((x + width/2, y), width/2, height,
                               facecolor=CELL_EMPTY, edgecolor='none')
        ax.add_patch(clip_right)

    elif state == 'second':
        fill = FancyBboxPatch((x, y), width, height,
                              boxstyle=f"round,pad=0,rounding_size={r}",
                              facecolor=ORANGE, edgecolor='none')
        ax.add_patch(fill)
        clip_left = Rectangle((x, y), width/2, height,
                              facecolor=CELL_EMPTY, edgecolor='none')
        ax.add_patch(clip_left)

    border = FancyBboxPatch((x, y), width, height,
                            boxstyle=f"round,pad=0,rounding_size={r}",
                            facecolor='none', edgecolor=CELL_BORDER, linewidth=1.2)
    ax.add_patch(border)

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

    days_uk = {0: 'Пн', 1: 'Вт', 2: 'Ср', 3: 'Чт', 4: 'Пт', 5: 'Сб', 6: 'Нд'}
    today_str = f"{days_uk[today_date.weekday()]}\n{today_date.strftime('%d.%m')}"
    tomorrow_str = f"{days_uk[tomorrow_date.weekday()]}\n{tomorrow_date.strftime('%d.%m')}"
    today_date_code = today_date.strftime('%Y-%m-%d')

    gpv_keys = [gpv_key] if gpv_key else sorted([k for k in today_data if k.startswith('GPV')])

    out_p = Path(out_path) if out_path else Path('.')
    out_p.mkdir(parents=True, exist_ok=True)
    hash_dir = out_p / 'hash'

    stats = {'checked': 0, 'skipped': 0, 'generated': 0}

    for gkey in gpv_keys:
        stats['checked'] += 1
        today_slots = today_data.get(gkey, {str(i): 'yes' for i in range(1, 25)})
        tomorrow_slots = tomorrow_data.get(gkey, {str(i): 'yes' for i in range(1, 25)})
        queue_name = sch_names.get(gkey, gkey)

        filename = format_gpv_filename(gkey)
        output_file = out_p / filename

        new_hash = calculate_data_hash(today_data, tomorrow_data, gkey)
        prev_hash = load_previous_hash(hash_dir, gkey)
        prev_date = load_previous_date(hash_dir, gkey)

        date_changed = (prev_date != today_date_code)
        hash_changed = (new_hash != prev_hash)

        if not output_file.exists() or hash_changed or date_changed:
            regenerate = True
        else:
            stats['skipped'] += 1
            regenerate = False

        if not regenerate:
            continue

        stats['generated'] += 1

        # Збільшені пропорції для читабельності в Telegram
        fig, ax = plt.subplots(figsize=(16, 6.2), dpi=180)
        fig.patch.set_facecolor(BG_COLOR)
        ax.set_facecolor(BG_COLOR)

        cell_w = 0.95
        cell_h = 0.85
        label_w = 2.4
        header_h = 1.7
        gap = 0.08

        total_width = label_w + 24 * (cell_w + gap)
        total_height = header_h + 2 * (cell_h + gap)

        # РЯДОК 2: Завтра
        y_pos = 0.1
        rect = FancyBboxPatch((0, y_pos), label_w - gap, cell_h,
                              boxstyle="round,pad=0,rounding_size=0.18",
                              facecolor=LABEL_BG, edgecolor=CELL_BORDER, linewidth=1.5)
        ax.add_patch(rect)
        ax.text((label_w - gap)/2, y_pos + cell_h/2, tomorrow_str, fontsize=14,
                ha='center', va='center', fontweight='bold', color=TEXT_DARK, linespacing=1.2)

        for i, slot_num in enumerate(SLOTS):
            x = label_w + i * (cell_w + gap)
            draw_rounded_slot(ax, x, y_pos, cell_w, cell_h, tomorrow_slots.get(str(slot_num), 'yes'))

        # РЯДОК 1: Сьогодні
        y_pos += cell_h + gap
        rect = FancyBboxPatch((0, y_pos), label_w - gap, cell_h,
                              boxstyle="round,pad=0,rounding_size=0.18",
                              facecolor=LABEL_BG, edgecolor=CELL_BORDER, linewidth=1.5)
        ax.add_patch(rect)
        ax.text((label_w - gap)/2, y_pos + cell_h/2, today_str, fontsize=14,
                ha='center', va='center', fontweight='bold', color=TEXT_DARK, linespacing=1.2)

        for i, slot_num in enumerate(SLOTS):
            x = label_w + i * (cell_w + gap)
            draw_rounded_slot(ax, x, y_pos, cell_w, cell_h, today_slots.get(str(slot_num), 'yes'))

        # РЯДОК 0: Часові проміжки
        y_pos += cell_h + gap
        rect = FancyBboxPatch((0, y_pos), label_w - gap, header_h,
                              boxstyle="round,pad=0,rounding_size=0.18",
                              facecolor=HEADER_BG, edgecolor=CELL_BORDER, linewidth=1.5)
        ax.add_patch(rect)
        ax.text((label_w - gap)/2, y_pos + header_h/2, 'Часові\nпроміжки', fontsize=12,
                ha='center', va='center', fontweight='bold', color=TEXT_DARK)

        for i in range(24):
            x = label_w + i * (cell_w + gap)
            rect = FancyBboxPatch((x, y_pos), cell_w, header_h,
                                  boxstyle="round,pad=0,rounding_size=0.18",
                                  facecolor=HEADER_BG, edgecolor=CELL_BORDER, linewidth=1.5)
            ax.add_patch(rect)
            ax.text(x + cell_w/2, y_pos + header_h/2, HOURS_TEXT[i], fontsize=13,
                    ha='center', va='center', fontweight='bold', color=TEXT_DARK, rotation=90)

        ax.set_xlim(-0.2, total_width + 0.2)
        ax.set_ylim(-0.8, total_height + 1.4)
        ax.invert_yaxis()
        ax.axis('off')

        # Заголовок
        fig.text(0.04, 0.93, 'Графік відключень (Вінницька обл.)', fontsize=20, fontweight='bold', color=TEXT_DARK)

        # Бейдж черги
        fig.text(0.96, 0.93, queue_name, fontsize=18, fontweight='bold', color=TEXT_DARK,
                 bbox=dict(boxstyle='round,pad=0.5,rounding_size=0.4', facecolor='#FFD700', edgecolor=TEXT_DARK, linewidth=1.8),
                 ha='right')

        # Легенда нижче графіку
        leg_y = -0.55
        spacing = 0.23

        # 1. Світло є
        draw_rounded_slot(ax, 0, leg_y, 0.7, 0.45, 'yes')
        ax.text(0.85, leg_y + 0.22, 'Світло є', fontsize=12, va='center', color=TEXT_DARK, fontweight='bold')

        # 2. Світла нема
        draw_rounded_slot(ax, 0 + spacing * 7.5, leg_y, 0.7, 0.45, 'no')
        ax.text(0.85 + spacing * 7.5, leg_y + 0.22, 'Без світла', fontsize=12, va='center', color=TEXT_DARK, fontweight='bold')

        # 3. Перші 30 хв
        draw_rounded_slot(ax, 0 + spacing * 15, leg_y, 0.7, 0.45, 'first')
        ax.text(0.85 + spacing * 15, leg_y + 0.22, 'Нема перші 30 хв', fontsize=12, va='center', color=TEXT_DARK, fontweight='bold')

        # 4. Другі 30 хв
        draw_rounded_slot(ax, 0 + spacing * 23, leg_y, 0.7, 0.45, 'second')
        ax.text(0.85 + spacing * 23, leg_y + 0.22, 'Нема другі 30 хв', fontsize=12, va='center', color=TEXT_DARK, fontweight='bold')

        # Дата оновлення
        if last_updated:
            ax.text(total_width, leg_y + 0.22, f'Оновлено: {last_updated}', fontsize=11,
                    ha='right', va='center', style='italic', color='#64748B')

        plt.savefig(output_file, facecolor=BG_COLOR, dpi=180, bbox_inches='tight', pad_inches=0.25)
        print(f"[OK] {output_file}")

        save_hash(hash_dir, gkey, new_hash)
        save_date(hash_dir, gkey, today_date_code)
        plt.close()

    print(f"\n[STATS] Checked: {stats['checked']}, Generated: {stats['generated']}, Skipped: {stats['skipped']}")

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--json', required=True)
    parser.add_argument('--gpv', default=None)
    parser.add_argument('--out', default=None)
    args = parser.parse_args()

    render_schedule(args.json, args.gpv, args.out)
