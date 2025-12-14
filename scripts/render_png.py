#!/usr/bin/env python3
"""
Schedule PNG Renderer - окремі таблиці (2 дні на одну чергу)
Генерує PNG тільки якщо дані змінилися (за хешем)
Хеші зберігаються в папці hash/
"""

import json
import argparse
from pathlib import Path
import sys
from datetime import datetime, timezone, timedelta
import hashlib

try:
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle
    import numpy as np
except ImportError:
    print("ERROR: pip install matplotlib")
    sys.exit(1)

ORANGE = '#FF8C00'
WHITE = '#FFFFFF'
GRAY_HEADER = '#E7E6E6'
GRAY_LABEL = '#D9D9D9'
BORDER = '#808080'

SLOTS = list(range(1, 25))
HOURS = [f'{i:02d}\n-\n{i+1:02d}' for i in range(24)]

# Таймзона Київ (UTC+2)
KYIV_TZ = timezone(timedelta(hours=2))

def format_gpv_filename(gpv_key):
    """
    Перетворює GPV2.1 -> gpv-2-1-emergency.png
    """
    cleaned = gpv_key.replace('GPV', '').replace('.', '-').lstrip('-')
    return f"gpv-{cleaned}-emergency.png"

def format_hash_filename(gpv_key):
    """
    Перетворює GPV2.1 -> gpv-2-1-emergency.hash
    """
    cleaned = gpv_key.replace('GPV', '').replace('.', '-').lstrip('-')
    return f"gpv-{cleaned}-emergency.hash"

def calculate_data_hash(today_data, tomorrow_data, gpv_key):
    """Розраховує SHA256 хеш даних для конкретної черги"""
    data_str = json.dumps({
        'today': today_data.get(gpv_key, {}),
        'tomorrow': tomorrow_data.get(gpv_key, {})
    }, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(data_str.encode()).hexdigest()

def load_previous_hash(hash_dir, gpv_key):
    """Завантажує попередній хеш з папки hash/"""
    hash_filename = format_hash_filename(gpv_key)
    hash_file = hash_dir / hash_filename
    
    if hash_file.exists():
        try:
            with open(hash_file, 'r', encoding='utf-8') as f:
                return f.read().strip()
        except Exception as e:
            print(f"[WARN] Could not read hash file {hash_file}: {e}")
    return None

def save_hash(hash_dir, gpv_key, data_hash):
    """Зберігає хеш даних у папку hash/"""
    hash_dir.mkdir(parents=True, exist_ok=True)
    
    hash_filename = format_hash_filename(gpv_key)
    hash_file = hash_dir / hash_filename
    
    try:
        with open(hash_file, 'w', encoding='utf-8') as f:
            f.write(data_hash)
    except Exception as e:
        print(f"[WARN] Could not save hash file {hash_file}: {e}")

def render_schedule(json_path, gpv_key=None, out_path=None):
    """Рендерити розклад"""
    
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    fact_data = data.get('fact', {}).get('data', {})
    sch_names = data.get('preset', {}).get('sch_names', {})
    last_updated = data.get('fact', {}).get('update', '')
    today_ts = str(data.get('fact', {}).get('today'))
    tomorrow_ts = str(int(today_ts) + 86400)
    
    today_data = fact_data.get(today_ts, {})
    tomorrow_data = fact_data.get(tomorrow_ts, {})
    
    # Отримуємо дати з таймзоною Київ
    today_date = datetime.fromtimestamp(int(today_ts), tz=KYIV_TZ)
    tomorrow_date = datetime.fromtimestamp(int(tomorrow_ts), tz=KYIV_TZ)
    
    # Форматуємо дати як "ДД місяць" (укр.)
    months_uk = {
        1: 'січня', 2: 'лютого', 3: 'березня', 4: 'квітня',
        5: 'травня', 6: 'червня', 7: 'липня', 8: 'серпня',
        9: 'вересня', 10: 'жовтня', 11: 'листопада', 12: 'грудня'
    }
    
    today_str = f'{today_date.day:02d} {months_uk[today_date.month]}'
    tomorrow_str = f'{tomorrow_date.day:02d} {months_uk[tomorrow_date.month]}'
    
    gpv_keys = [gpv_key] if gpv_key else sorted([k for k in today_data if k.startswith('GPV')])
    
    # Створюємо папку images/Vinnytsiaoblenerho та папку hash всередині неї
    if out_path:
        out_p = Path(out_path)
        out_p.mkdir(parents=True, exist_ok=True)
        hash_dir = out_p / 'hash'
    else:
        out_p = Path('.')
        hash_dir = out_p / 'hash'
    
    stats = {
        'checked': 0,
        'skipped': 0,
        'generated': 0,
    }
    
    for gkey in gpv_keys:
        stats['checked'] += 1
        
        today_slots = today_data.get(gkey, {str(i): 'yes' for i in range(1, 25)})
        tomorrow_slots = tomorrow_data.get(gkey, {str(i): 'yes' for i in range(1, 25)})
        queue_name = sch_names.get(gkey, gkey)
        
        # === ПЕРЕВІРЯЄМО ХЕШ ===
        filename = format_gpv_filename(gkey)
        output_file = out_p / filename
        
        # Розраховуємо новий хеш
        new_hash = calculate_data_hash(today_data, tomorrow_data, gkey)
        
        # Завантажуємо попередній хеш
        prev_hash = load_previous_hash(hash_dir, gkey)
        
        # Якщо хеші збігаються, пропускаємо генерацію
        if new_hash == prev_hash and output_file.exists():
            print(f"[SKIP] {filename} (no data changes)")
            stats['skipped'] += 1
            continue
        
        stats['generated'] += 1
        
        # === ГЕНЕРУЄМО PNG ===
        fig, ax = plt.subplots(figsize=(20, 3.5), dpi=100)
        fig.patch.set_facecolor(WHITE)
        ax.set_facecolor(WHITE)
        
        # Розміри клітинок
        cell_w = 1.0
        cell_h = 0.5
        label_w = 2.0
        header_h = 1.0
        
        # Розміри таблиці для вирівнювання
        table_width = label_w + 24 * cell_w  # 26 одиниць
        table_height = header_h + 2 * cell_h
        
        # Y позиція
        y_pos = 0
        
        # === РЯДОК 0: Заголовки часів ===
        # Ліва клітинка (лейбл "Дата")
        rect = Rectangle((0, y_pos), label_w, header_h, linewidth=1, edgecolor=BORDER, facecolor=GRAY_HEADER)
        ax.add_patch(rect)
        ax.text(label_w/2, y_pos + header_h/2, 'Дата', fontsize=12, ha='center', va='center',
               fontweight='bold', color='#000000')
        
        # Години
        for i in range(24):
            x = label_w + i * cell_w
            rect = Rectangle((x, y_pos), cell_w, header_h, linewidth=1, edgecolor=BORDER, facecolor=GRAY_HEADER)
            ax.add_patch(rect)
            ax.text(x + cell_w/2, y_pos + header_h/2, HOURS[i], fontsize=11, ha='center', va='center',
                   fontweight='bold', color='#000000', linespacing=1.5)
        
        y_pos += header_h
        
        # === РЯДОК 1: Сьогодні ===
        # Ліва клітинка
        rect = Rectangle((0, y_pos), label_w, cell_h, linewidth=1, edgecolor=BORDER, facecolor=GRAY_LABEL)
        ax.add_patch(rect)
        ax.text(label_w/2, y_pos + cell_h/2, today_str, fontsize=12, ha='center', va='center',
               fontweight='bold', color='#000000')
        
        # Слоти сьогодні
        for i, slot_num in enumerate(SLOTS):
            x = label_w + i * cell_w
            slot_key = str(slot_num)
            state = today_slots.get(slot_key, 'yes')
            
            # Спочатку білий фон для всіх
            rect = Rectangle((x, y_pos), cell_w, cell_h, linewidth=1, edgecolor=BORDER, facecolor=WHITE)
            ax.add_patch(rect)
            
            # Заливаємо за станом
            if state == 'no':
                # Повністю оранжева
                rect_fill = Rectangle((x, y_pos), cell_w, cell_h, linewidth=0, facecolor=ORANGE)
                ax.add_patch(rect_fill)
            elif state == 'first':
                # Ліва половина оранжева
                rect_left = Rectangle((x, y_pos), cell_w/2, cell_h, linewidth=0, facecolor=ORANGE)
                ax.add_patch(rect_left)
            elif state == 'second':
                # Права половина оранжева
                rect_right = Rectangle((x + cell_w/2, y_pos), cell_w/2, cell_h, linewidth=0, facecolor=ORANGE)
                ax.add_patch(rect_right)
            
            # Бордюр зверху
            rect_border = Rectangle((x, y_pos), cell_w, cell_h, linewidth=1, edgecolor=BORDER, facecolor='none')
            ax.add_patch(rect_border)
        
        y_pos += cell_h
        
        # === РЯДОК 2: Завтра ===
        # Ліва клітинка
        rect = Rectangle((0, y_pos), label_w, cell_h, linewidth=1, edgecolor=BORDER, facecolor=GRAY_LABEL)
        ax.add_patch(rect)
        ax.text(label_w/2, y_pos + cell_h/2, tomorrow_str, fontsize=12, ha='center', va='center',
               fontweight='bold', color='#000000')
        
        # Слоти завтра
        for i, slot_num in enumerate(SLOTS):
            x = label_w + i * cell_w
            slot_key = str(slot_num)
            state = tomorrow_slots.get(slot_key, 'yes')
            
            # Спочатку білий фон для всіх
            rect = Rectangle((x, y_pos), cell_w, cell_h, linewidth=1, edgecolor=BORDER, facecolor=WHITE)
            ax.add_patch(rect)
            
            # Заливаємо за станом
            if state == 'no':
                # Повністю оранжева
                rect_fill = Rectangle((x, y_pos), cell_w, cell_h, linewidth=0, facecolor=ORANGE)
                ax.add_patch(rect_fill)
            elif state == 'first':
                # Ліва половина оранжева
                rect_left = Rectangle((x, y_pos), cell_w/2, cell_h, linewidth=0, facecolor=ORANGE)
                ax.add_patch(rect_left)
            elif state == 'second':
                # Права половина оранжева
                rect_right = Rectangle((x + cell_w/2, y_pos), cell_w/2, cell_h, linewidth=0, facecolor=ORANGE)
                ax.add_patch(rect_right)
            
            # Бордюр
            rect_border = Rectangle((x, y_pos), cell_w, cell_h, linewidth=1, edgecolor=BORDER, facecolor='none')
            ax.add_patch(rect_border)
        
        ax.set_xlim(0, table_width)
        ax.set_ylim(0, table_height)
        ax.invert_yaxis()
        
        ax.set_xticks([])
        ax.set_yticks([])
        ax.margins(0)
        for spine in ax.spines.values():
            spine.set_visible(False)
        
        # === ПОЗИЦІОНУВАННЯ ЕЛЕМЕНТІВ НА РИСУНКУ ===
        
        # Заголовок "Графік відключень:" 
        fig.text(0.15, 0.97, 'Графік відключень для Вінницька область', fontsize=18, fontweight='bold')
        
        # Етикетка черги
        fig.text(0.85, 0.97, queue_name, fontsize=18, fontweight='bold',
                bbox=dict(boxstyle='round,pad=0.5', facecolor='#FFD700', edgecolor='#000000', linewidth=1.5),
                ha='right')
        
        # === ЛЕГЕНДА З КЛІТИНКАМИ АНАЛОГІЧНО ТАБЛИЦІ ===
        legend_y = 0.005  # Низько
        legend_x_center = 0.35  # Лівіше від центру, але в межах таблиці
        
        # Розміри клітинок в легенді (пропорційні до таблиці)
        table_fig_width = 0.9 - 0.05  # 0.85
        cell_w_fig = table_fig_width / table_width  # пропорція cell_w
        cell_h_fig = (0.85 - 0.15) / table_height * cell_h  # пропорція cell_h (без заголовка)
        
        # Проміжок між елементами легенди
        spacing = 0.09
        
        # Елемент 1: Пуста біла клітинка - "Світло є"
        x1 = legend_x_center - 1.8 * spacing
        rect = Rectangle((x1 - cell_w_fig/2, legend_y - cell_h_fig/2), cell_w_fig, cell_h_fig, 
                        linewidth=0.5, edgecolor=BORDER, facecolor=WHITE, 
                        transform=fig.transFigure, clip_on=False)
        fig.patches.append(rect)
        fig.text(x1 + cell_w_fig/2 + 0.005, legend_y, 'Світло є', fontsize=11, va='center')
        
        # Елемент 2: Повністю оранжева клітинка - "Світла нема"
        x2 = legend_x_center - 0.6 * spacing
        rect = Rectangle((x2 - cell_w_fig/2, legend_y - cell_h_fig/2), cell_w_fig, cell_h_fig, 
                        linewidth=0.5, edgecolor=BORDER, facecolor=ORANGE, 
                        transform=fig.transFigure, clip_on=False)
        fig.patches.append(rect)
        fig.text(x2 + cell_w_fig/2 + 0.005, legend_y, 'Світла нема', fontsize=11, va='center')
        
        # Елемент 3: Ліва половина оранжева - "Світла нема перші 30 хв."
        x3 = legend_x_center + 0.6 * spacing
        # Ліва половина біла
        rect_left = Rectangle((x3 - cell_w_fig/2, legend_y - cell_h_fig/2), cell_w_fig/2, cell_h_fig, 
                             linewidth=0, facecolor=WHITE, 
                             transform=fig.transFigure, clip_on=False)
        fig.patches.append(rect_left)
        # Права половина оранжева
        rect_right = Rectangle((x3, legend_y - cell_h_fig/2), cell_w_fig/2, cell_h_fig, 
                              linewidth=0, facecolor=ORANGE, 
                              transform=fig.transFigure, clip_on=False)
        fig.patches.append(rect_right)
        # Бордюр
        rect_border = Rectangle((x3 - cell_w_fig/2, legend_y - cell_h_fig/2), cell_w_fig, cell_h_fig, 
                               linewidth=0.5, edgecolor=BORDER, facecolor='none', 
                               transform=fig.transFigure, clip_on=False)
        fig.patches.append(rect_border)
        fig.text(x3 + cell_w_fig/2 + 0.005, legend_y, 'Світла нема\nперші 30 хв.', fontsize=11, va='center')
        
        # Елемент 4: Права половина оранжева - "Світла нема другі 30 хв."
        x4 = legend_x_center + 1.8 * spacing
        # Ліва половина оранжева
        rect_left = Rectangle((x4 - cell_w_fig/2, legend_y - cell_h_fig/2), cell_w_fig/2, cell_h_fig, 
                             linewidth=0, facecolor=ORANGE, 
                             transform=fig.transFigure, clip_on=False)
        fig.patches.append(rect_left)
        # Права половина біла
        rect_right = Rectangle((x4, legend_y - cell_h_fig/2), cell_w_fig/2, cell_h_fig, 
                              linewidth=0, facecolor=WHITE, 
                              transform=fig.transFigure, clip_on=False)
        fig.patches.append(rect_right)
        # Бордюр
        rect_border = Rectangle((x4 - cell_w_fig/2, legend_y - cell_h_fig/2), cell_w_fig, cell_h_fig, 
                               linewidth=0.5, edgecolor=BORDER, facecolor='none', 
                               transform=fig.transFigure, clip_on=False)
        fig.patches.append(rect_border)
        fig.text(x4 + cell_w_fig/2 + 0.005, legend_y, 'Світла нема\nдругі 30 хв.', fontsize=11, va='center')
        
        # Дата оновлення
        if last_updated:
            fig.text(0.8, 0.001, f'Опубліковано {last_updated}', fontsize=11, ha='right', style='italic')
        
        # === ЗБЕРЕЖЕННЯ PNG ===
        plt.savefig(output_file, facecolor=WHITE, dpi=150, bbox_inches='tight', pad_inches=0.13)
        print(f"[OK] {output_file}")
        
        # Зберігаємо хеш в папку hash/
        save_hash(hash_dir, gkey, new_hash)
        
        plt.close()
    
    # Вивід статистики
    print(f"\n[STATS] Checked: {stats['checked']}, Generated: {stats['generated']}, Skipped: {stats['skipped']}")

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--json', required=True)
    parser.add_argument('--gpv', default=None)
    parser.add_argument('--out', default=None)
    args = parser.parse_args()
    
    render_schedule(args.json, args.gpv, args.out)
