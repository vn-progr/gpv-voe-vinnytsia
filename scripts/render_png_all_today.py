#!/usr/bin/env python3
"""
Schedule PNG Renderer - класична зведена таблиця усіх графіків на сьогодні
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

def calculate_all_today_hash(today_data):
    """Розраховує SHA256 хеш всіх даних на сьогодні"""
    data_str = json.dumps(today_data, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(data_str.encode()).hexdigest()

def load_previous_hash(hash_dir):
    """Завантажує попередній хеш з папки hash/"""
    hash_file = hash_dir / 'gpv-all-today.hash'
    if hash_file.exists():
        try:
            with open(hash_file, 'r', encoding='utf-8') as f:
                return f.read().strip()
        except Exception as e:
            print(f"[WARN] Could not read hash file {hash_file}: {e}")
    return None

def load_previous_date(hash_dir):
    """Завантажує попередню дату з файлу дати"""
    date_file = hash_dir / 'gpv-all-today.date'
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
    hash_file = hash_dir / 'gpv-all-today.hash'
    try:
        with open(hash_file, 'w', encoding='utf-8') as f:
            f.write(data_hash)
    except Exception as e:
        print(f"[WARN] Could not save hash file {hash_file}: {e}")

def save_date(hash_dir, date_str):
    """Зберігає поточну дату у файл для перевірки на наступний день"""
    hash_dir.mkdir(parents=True, exist_ok=True)
    date_file = hash_dir / 'gpv-all-today.date'
    try:
        with open(date_file, 'w', encoding='utf-8') as f:
            f.write(date_str)
    except Exception as e:
        print(f"[WARN] Could not save date file {date_file}: {e}")

def render_all_schedules(json_path, out_path=None, force=False):
    """Рендерити всі графіки на сьогодні в одну таблицю"""
    
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    fact_data = data.get('fact', {}).get('data', {})
    sch_names = data.get('preset', {}).get('sch_names', {})
    last_updated = data.get('fact', {}).get('update', '')
    today_ts = str(data.get('fact', {}).get('today'))

    today_data = fact_data.get(today_ts, {})

    out_p = Path(out_path) if out_path else Path('.')
    out_p.mkdir(parents=True, exist_ok=True)
    hash_dir = out_p / 'hash'

    new_hash = calculate_all_today_hash(today_data)
    prev_hash = load_previous_hash(hash_dir)
    output_file = out_p / 'gpv-all-today.png'

    today_date = datetime.fromtimestamp(int(today_ts), tz=KYIV_TZ)
    today_date_code = today_date.strftime('%Y-%m-%d')
    prev_date = load_previous_date(hash_dir)

    date_changed = (prev_date != today_date_code)
    hash_changed = (new_hash != prev_hash)

    if force:
        print(f"[REGEN] gpv-all-today.png (forced)")
        regenerate = True
    elif not output_file.exists():
        print(f"[REGEN] gpv-all-today.png (file not found)")
        regenerate = True
    elif hash_changed:
        print(f"[REGEN] gpv-all-today.png (hash changed)")
        regenerate = True
    elif date_changed:
        print(f"[REGEN] gpv-all-today.png (date changed: {prev_date} → {today_date_code})")
        regenerate = True
    else:
        print(f"[SKIP] gpv-all-today.png (no changes)")
        regenerate = False

    if not regenerate:
        return

    months_uk = {
        1: 'січня', 2: 'лютого', 3: 'березня', 4: 'квітня',
        5: 'травня', 6: 'червня', 7: 'липня', 8: 'серпня',
        9: 'вересня', 10: 'жовтня', 11: 'листопада', 12: 'грудня'
    }
    today_str = f'{today_date.day:02d} {months_uk[today_date.month]}'

    gpv_keys = sorted([k for k in today_data if k.startswith('GPV')])
    num_schedules = len(gpv_keys)

    if num_schedules == 0:
        print("[SKIP] gpv-all-today.png (No GPV schedules found)")
        return

    print(f"[GENERATE] gpv-all-today.png for {today_date.strftime('%d.%m.%Y')}")

    # Розміри клітинок та пропорції
    cell_w = 1.0
    cell_h = 0.55
    label_w = 2.4
    header_h = 1.3

    table_width = label_w + 24 * cell_w
    table_height = header_h + num_schedules * cell_h

    # Динамічна висота рисунка залежно від кількості черг
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
        slots = today_data.get(gpv_key, {str(i): 'yes' for i in range(1, 25)})
        queue_name = sch_names.get(gpv_key, gpv_key)

        # Ліва клітинка з назвою черги
        rect = Rectangle((0, y_pos), label_w, cell_h, linewidth=1.2, edgecolor=BORDER, facecolor=GRAY_LABEL)
