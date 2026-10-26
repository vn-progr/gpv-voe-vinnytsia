#!/usr/bin/env python3
"""
Schedule PNG Renderer - класична зведена таблиця усіх графіків на завтра
Оптимізовано для Telegram (читабельність на смартфонах)
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
    from matplotlib.patches import Rectangle
except ImportError:
    print("ERROR: pip install matplotlib")
    sys.exit(1)

# Кольори
ORANGE = '#FF8C00'
WHITE = '#FFFFFF'
GRAY_HEADER = '#EAEAEA'
GRAY_LABEL = '#F2F2F2'
BORDER = '#707070'
TEXT_DARK = '#000000'

SLOTS = list(range(1, 25))
HOURS_TEXT = [f'{i:02d}\n-\n{i+1:02d}' for i in range(24)]

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

    # Розміри клітинок та пропорції
    cell_w = 1.0
    cell_h = 0.55
    label_w = 2.4
    header_h = 1.3

    table_width = label_w + 24 * cell_w
    table_height = header_h + num_schedules * cell_h

    fig_height = 2.0 + (num_schedules * 0.45)

    fig, ax = plt.subplots(figsize=(18, fig_height), dpi=160)
    fig.patch.set_facecolor(WHITE)
    ax.set_facecolor(WHITE)

    y_pos = 0

    # === РЯДОК 0: Шапка часу (ЗВЕРХУ) ===
    rect = Rectangle((0, y_pos), label_w, header_h, linewidth=1.2, edgecolor=BORDER, facecolor=GRAY_HEADER)
    ax.add_patch(rect)
    ax.text(label_w/2, y_pos + header_h/2, 'Черга', fontsize=12, ha='center', va='center', fontweight='bold', color=TEXT_DARK)

    for i in range(24):
        x = label_w + i * cell_w
        rect = Rectangle((x, y_pos), cell_w, header_h, linewidth=1.2, edgecolor=BORDER, facecolor=GRAY_HEADER)
        ax.add_patch(rect)
        ax.text(x + cell_w/2, y_pos + header_h/2, HOURS_TEXT[i], fontsize=10, ha='center', va='center',
                fontweight='bold', color=TEXT_DARK, linespacing=1.2)

    y_pos += header_h

    # === РЯДКИ З ЧЕРГАМИ (ВІД 1.1 ДО 6.2) ===
    for gpv_key in gpv_keys:
        slots = tomorrow_data.get(gpv_key, {str(i): 'yes' for i in range(1, 25)})
        queue_name = sch_names.get(gpv_key, gpv_key)

        rect = Rectangle((0, y_pos), label_w, cell_h, linewidth=1.2, edgecolor=BORDER, facecolor=GRAY_LABEL)
        ax.add_patch(rect)
        ax.text(label_w/2, y_pos + cell_h/2, queue_name, fontsize=11, ha='center', va='center', fontweight='bold', color=TEXT_DARK)

        for i, slot_num in enumerate(SLOTS):
            x = label_w + i * cell_w
            state = slots.get(str(slot_num), 'yes')

            rect = Rectangle((x, y_pos), cell_w, cell_h, linewidth=1.2, edgecolor=BORDER, facecolor=WHITE)
            ax.add_patch(rect)

            if state == 'no':
                ax.add_patch(Rectangle((x, y_pos), cell_w, cell_h, linewidth=0, facecolor=ORANGE))
            elif state == 'first':
                ax.add_patch(Rectangle((x, y_pos), cell_w/2, cell_h, linewidth=0, facecolor=ORANGE))
            elif state == 'second':
                ax.add_patch(Rectangle((x + cell_w/2, y_pos), cell_w/2, cell_h, linewidth=0, facecolor=ORANGE))

            ax.add_patch(Rectangle((x, y_pos), cell_w, cell_h, linewidth=1.2, edgecolor=BORDER, facecolor='none'))

        y_pos += cell_h

    ax.set_xlim(0, table_width)
    ax.set_ylim(0, table_height)
    ax.invert_yaxis()
    ax.axis('off')

    # === ХЕДЕР ЗГОРИ ===
    fig.text(0.05, 0.96, f'Графік відключень на завтра (Вінницька обл.) — {tomorrow_str}',
             fontsize=17, fontweight='bold', color=TEXT_DARK)

    # === ЛЕГЕНДА ЗНИЗУ ПІД ТАБЛИЦЕЮ ===
    legend_y = 0.02
    fig.patches.clear()

    # 1. Світло є
    rect1 = Rectangle((0.08, legend_y), 0.03, 0.035, linewidth=1, edgecolor=BORDER, facecolor=WHITE, transform=fig.transFigure)
    fig.patches.append(rect1)
    fig.text(0.12, legend_y + 0.015, 'Світло є', fontsize=11, va='center', color=TEXT_DARK)

    # 2. Світла нема
    rect2 = Rectangle((0.26, legend_y), 0.03, 0.035, linewidth=1, edgecolor=BORDER, facecolor=ORANGE, transform=fig.transFigure)
    fig.patches.append(rect2)
    fig.text(0.30, legend_y + 0.015, 'Світла нема', fontsize=11, va='center', color=TEXT_DARK)

    # 3. Перші 30 хв
    rect3_bg = Rectangle((0.45, legend_y), 0.03, 0.035, linewidth=1, edgecolor=BORDER, facecolor=WHITE, transform=fig.transFigure)
    rect3_fill = Rectangle((0.45, legend_y), 0.015, 0.035, linewidth=0, facecolor=ORANGE, transform=fig.transFigure)
    fig.patches.extend([rect3_bg, rect3_fill])
    fig.text(0.49, legend_y + 0.015, 'Світла нема перші 30 хв.', fontsize=11, va='center', color=TEXT_DARK)

    # 4. Другі 30 хв
    rect4_bg = Rectangle((0.68, legend_y), 0.03, 0.035, linewidth=1, edgecolor=BORDER, facecolor=WHITE, transform=fig.transFigure)
    rect4_fill = Rectangle((0.68 + 0.015, legend_y), 0.015, 0.035, linewidth=0, facecolor=ORANGE, transform=fig.transFigure)
    fig.patches.extend([rect4_bg, rect4_fill])
    fig.text(0.72, legend_y + 0.015, 'Світла нема другі 30 хв.', fontsize=11, va='center', color=TEXT_DARK)

    if last_updated:
        fig.text(0.95, 0.005, f'Оновлено {last_updated}', fontsize=10, ha='right', style='italic', color='#555555')

    plt.savefig(output_file, facecolor=WHITE, dpi=160, bbox_inches='tight', pad_inches=0.15)
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
