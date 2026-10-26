#!/usr/bin/env python3
"""
Schedule PNG Renderer - класична чітка таблиця (2 дні на одну чергу)
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

def format_gpv_filename(gpv_key):
    """Перетворює GPV2.1 -> gpv-2-1-emergency.png"""
    cleaned = gpv_key.replace('GPV', '').replace('.', '-').lstrip('-')
    return f"gpv-{cleaned}-emergency.png"

def format_hash_filename(gpv_key):
    """Перетворює GPV2.1 -> gpv-2-1-emergency.hash"""
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
    hash_file = hash_dir / format_hash_filename(gpv_key)
    if hash_file.exists():
        try:
            with open(hash_file, 'r', encoding='utf-8') as f:
                return f.read().strip()
        except Exception:
            pass
    return None

def load_previous_date(hash_dir, gpv_key):
    """Завантажує попередню дату з файлу дати"""
    date_file = hash_dir / format_hash_filename(gpv_key).replace('.hash', '.date')
    if date_file.exists():
        try:
            with open(date_file, 'r', encoding='utf-8') as f:
                return f.read().strip()
        except Exception:
            pass
    return None

def save_hash(hash_dir, gpv_key, data_hash):
    """Зберігає хеш даних у папку hash/"""
    hash_dir.mkdir(parents=True, exist_ok=True)
    with open(hash_dir / format_hash_filename(gpv_key), 'w', encoding='utf-8') as f:
        f.write(data_hash)

def save_date(hash_dir, gpv_key, date_str):
    """Зберігає поточну дату у файл для перевірки на наступний день"""
    hash_dir.mkdir(parents=True, exist_ok=True)
    date_file = hash_dir / format_hash_filename(gpv_key).replace('.hash', '.date')
    with open(date_file, 'w', encoding='utf-8') as f:
        f.write(date_str)

def render_schedule(json_path, gpv_key=None, out_path=None, force=False):
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

    today_date = datetime.fromtimestamp(int(today_ts), tz
