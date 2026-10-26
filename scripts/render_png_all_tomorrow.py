#!/usr/bin/env python3
"""
Schedule PNG Renderer - зведена таблиця усіх графіків на завтра
Генерує PNG тільки якщо дані змінилися (за хешем) АБО якщо змінилася дата
Хеші та дати зберігаються в папці hash/
"""

import json
import argparse
from pathlib import Path
import sys
from datetime import datetime, timezone, timedelta
import hashlib

import matplotlib
matplotlib.use('Agg')  # Для роботи в headless режимі (наприклад, на GitHub Actions)

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

# Таймзона Київ (UTC+2)
KYIV_TZ = timezone(timedelta(hours=2))

def calculate_all_tomorrow_hash(tomorrow_data):
    """Розраховує SHA256 хеш всіх даних на завтра"""
    data_str = json.dumps(tomorrow_data, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(data_str.encode()).hexdigest()

def load_previous_hash(hash_dir):
    """Завантажує попередній хеш з папки hash/"""
    hash_file = hash_dir / 'gpv-all-tomorrow.hash'
    if hash_file.exists():
        try:
            with open(hash_file, 'r', encoding='utf-8') as f:
                return f.read().strip()
        except Exception as e:
            print(f"[WARN] Could not read hash file {hash_file}: {e}")
    return None

def load_previous_date(hash_dir):
    """Завантажує попередню дату з файлу дати"""
    date_file = hash_dir / 'gpv-all-tomorrow.date'
    if date_file.exists():
        try:
            with open(date_file, 'r', encoding='utf-8') as f:
                return f.read().strip()
        except Exception as e:
            print(f"[WARN] Could not read date file {date_file}: {e}")
    return None

def save_hash(hash_dir, data_hash):
    """Зберігає хеш даних у папку hash/"""
    hash_dir.mkdir(parents=True, exist_ok=True)
    hash_file = hash_dir / 'gpv-all-tomorrow.hash'
    try:
        with open(hash_file, 'w', encoding='utf-8') as f:
            f.write(data_hash)
    except Exception as e:
        print(f"[WARN] Could not save hash file {hash_file}: {e}")

def save_date(hash_dir, date_str):
    """Зберігає поточну дату у файл для перевірки на наступний день"""
    hash_dir.mkdir(parents=True, exist_ok=True)
    date_file = hash_dir / 'gpv-all-tomorrow.date'
    try:
        with open(date_file, 'w', encoding='utf-8') as f:
            f.write(date_str)
    except Exception as e:
        print(f"[WARN] Could not save date file {date_file}: {e}")

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

def render_all_tomorrow_schedules(json_path, out_path=None, force=False):
    """Рендерити всі графіки на завтра в одну таблицю"""
    
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    fact_data = data.get('fact', {}).get('data', {})
    sch_names = data.get('preset', {}).get('sch_names', {})
    last_updated = data.get('fact', {}).get('update', '')
    
    today_ts = str(data.get('fact', {}).get('today'))
    tomorrow_ts = str(int(today_ts) + 86400)
    
    tomorrow_data = fact_data.get(tomorrow_ts, {})
    tomorrow_date = datetime.fromtimestamp(int(tomorrow_ts), tz=KYIV_TZ)
    
    out_p = Path(out_path) if out_path else Path('.')
    out_p.mkdir(parents=True, exist_ok=True)
    hash_dir = out_p / 'hash'

    new_hash = calculate_all_tomorrow_hash(tomorrow_data)
    prev_hash = load_previous_hash(hash_dir)
    output_file = out_p / 'gpv-all-tomorrow.png'

    tomorrow_date_code = tomorrow_date.strftime('%Y-%m-%d')
    prev_date = load_previous_date(hash_dir)

    date_changed = (prev_date != tomorrow_date_code)
    hash_changed = (new_hash != prev_hash)

    if force:
        print(f"[REGEN] gpv-all-tomorrow.png (forced)")
        regenerate = True
    elif not output_file.exists():
        print(f"[REGEN] gpv-all-tomorrow.png (file not found)")
        regenerate = True
    elif hash_changed:
        print(f"[REGEN] gpv-all-tomorrow.png (hash changed)")
        regenerate = True
    elif date_changed:
        print(f"[REGEN] gpv-all-tomorrow.png (date changed: {prev_date} → {tomorrow_date_code})")
        regenerate = True
    else:
        print(f"[SKIP] gpv-all-tomorrow.png (no changes)")
        regenerate = False

    if not regenerate:
        return

    months_uk = {
        1: 'січня', 2: 'лютого', 3: 'березня', 4: 'квітня',
        5: 'травня', 6: 'червня', 7: 'липня', 8: 'серпня',
        9: 'вересня', 10: 'жовтня', 11: 'листопада', 12: 'грудня'
    }
    tomorrow_str = f'{tomorrow_date.day:02d} {months_uk[tomorrow_date.month]}'

    gpv_keys = sorted([k for k in tomorrow_data if k.startswith('GPV')])
    num_schedules = len(gpv_keys)

    if num_schedules == 0:
        print("[SKIP] gpv-all-tomorrow.png (No GPV schedules found)")
        return

    print(f"[GENERATE] gpv-all-tomorrow.png for {tomorrow_date.strftime('%d.%m.%Y')}")

    # Геометрія таблиці
    cell_w = 0.95
    cell_h = 0.65
    label_w = 2.4
    header_h = 1.7
    gap = 0.08

    total_width = label_w + 24 * (cell_w + gap)
    total_height = header_h + num_schedules * (cell_h + gap)

    fig_height = 2.5 + (num_schedules * 0.75)

    fig, ax = plt.subplots(figsize=(16, fig_height), dpi=180)
    fig.patch.set_facecolor(BG_COLOR)
    ax.set_facecolor(BG_COLOR)

    y_pos = 0.1

    # РЯДКИ з ГРАФІКАМИ
    for gpv_key in reversed(gpv_keys):
        slots = tomorrow_data.get(gpv_key, {str(i): 'yes' for i in range(1, 25)})
        queue_name = sch_names.get(gpv_key, gpv_key)

        rect = FancyBboxPatch((0, y_pos), label_w - gap, cell_h,
                              boxstyle="round,pad=0,rounding_size=0.18",
                              facecolor=LABEL_BG, edgecolor=CELL_BORDER, linewidth=1.5)
        ax.add_patch(rect)
        ax.text((label_w - gap)/2, y_pos + cell_h/2, queue_name, fontsize=13,
                ha='center', va='center', fontweight='bold', color=TEXT_DARK)

        for i, slot_num in enumerate(SLOTS):
            x = label_w + i * (cell_w + gap)
            draw_rounded_slot(ax, x, y_pos, cell_w, cell_h, slots.get(str(slot_num), 'yes'))

        y_pos += cell_h + gap

    # РЯДОК 0: Часові проміжки (зверху)
    rect = FancyBboxPatch((0, y_pos), label_w - gap, header_h,
                          boxstyle="round,pad=0,rounding_size=0.18",
                          facecolor=HEADER_BG, edgecolor=CELL_BORDER, linewidth=1.5)
    ax.add_patch(rect)
    ax.text((label_w - gap)/2, y_pos + header_h/2, 'Черга', fontsize=13,
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
    fig.text(0.04, 0.95, f'Графік відключень на завтра (Вінницька обл.) — {tomorrow_str}',
             fontsize=18, fontweight='bold', color=TEXT_DARK)

    # Легенда під таблицею
    leg_y = -0.6
    spacing = 0.23

    draw_rounded_slot(ax, 0, leg_y, 0.7, 0.45, 'yes')
    ax.text(0.85, leg_y + 0.22, 'Світло є', fontsize=12, va='center', color=TEXT_DARK, fontweight='bold')

    draw_rounded_slot(ax, 0 + spacing * 7.5, leg_y, 0.7, 0.45, 'no')
    ax.text(0.85 + spacing * 7.5, leg_y + 0.22, 'Без світла', fontsize=12, va='center', color=TEXT_DARK, fontweight='bold')

    draw_rounded_slot(ax, 0 + spacing * 15, leg_y, 0.7, 0.45, 'first')
    ax.text(0.85 + spacing * 15, leg_y + 0.22, 'Нема перші 30 хв', fontsize=12, va='center', color=TEXT_DARK, fontweight='bold')

    draw_rounded_slot(ax, 0 + spacing * 23, leg_y, 0.7, 0.45, 'second')
    ax.text(0.85 + spacing * 23, leg_y + 0.22, 'Нема другі 30 хв', fontsize=12, va='center', color=TEXT_DARK, fontweight='bold')

    if last_updated:
        ax.text(total_width, leg_y + 0.22, f'Оновлено: {last_updated}', fontsize=11,
                ha='right', va='center', style='italic', color='#64748B')

    plt.savefig(output_file, facecolor=BG_COLOR, dpi=180, bbox_inches='tight', pad_inches=0.25)
    print(f"[OK] Saved {output_file}")

    save_hash(hash_dir, new_hash)
    save_date(hash_dir, tomorrow_date_code)
    plt.close()

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--json', required=True)
    parser.add_argument('--out', default=None)
    parser.add_argument('--force', action='store_true', help='Примусова регенерація без перевірки хешу')
    args = parser.parse_args()

    render_all_tomorrow_schedules(args.json, args.out, force=args.force)
