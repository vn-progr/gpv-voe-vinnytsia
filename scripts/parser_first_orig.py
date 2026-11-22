#!/usr/bin/env python3
"""
🔌 GPV VOE Вінниця - BezSvitla Parser
Парсить 12 черг → data/Vinnytsiaoblenerho.json (GPV формат з first/second)
"""
import json
import os
import time
import sys
import re
from datetime import datetime, timezone, timedelta
import hashlib
from bs4 import BeautifulSoup
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

def log(msg):
    print(msg)
    sys.stdout.flush()

for lib in ['requests', 'bs4']:
    try:
        __import__(lib)
    except ImportError:
        print(f"❌ ERROR: pip install -r requirements.txt")
        sys.exit(1)

QUEUE_MAPPING = {
    "1.1": "1.1",
    "1.2": "1.2",
    "2.1": "2.1",
    "2.2": "2.2",
    "3.1": "3.1",
    "3.2": "3.2",
    "4.1": "4.1",
    "4.2": "4.2",
    "5.1": "5.1",
    "5.2": "5.2",
    "6.1": "6.1",
    "6.2": "6.2"
}

QUEUE_TO_GPV = {k: f"GPV{k}" for k in QUEUE_MAPPING}
ALL_QUEUE_KEYS = list(QUEUE_MAPPING)
BASE_URL = "https://bezsvitla.com.ua/vinnytska-oblast/cherha-{queue}"
TOMORROW_URL = BASE_URL + "/grafik-na-zavtra"
KYIV_TZ = timezone(timedelta(hours=2))

def create_session():
    s = requests.Session()
    retry_strategy = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
    s.mount('http://', HTTPAdapter(max_retries=retry_strategy))
    s.mount('https://', HTTPAdapter(max_retries=retry_strategy))
    s.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'text/html,application/xhtml+xml,*/*;q=0.9',
        'Accept-Language': 'uk,en;q=0.9',
    })
    return s

def parse_time_slot(t):
    m = re.match(r'(\d{2}):(\d{2})\s*[––\-\s–]\s*(\d{2}):(\d{2})', t)
    return tuple(map(int, m.groups())) if m else None

def round_minutes_to_half_hour(minutes):
    """< 30 → 0, >= 30 → 30"""
    return 30 if minutes >= 30 else 0

def hour_to_slot(h):
    """Слот N = (N-1):00 до N:00"""
    return 1 if h == 0 else h + 1

def parse_html_schedule(html):
    """
    Парсить HTML і повертає слоти 1-24 зі станами:
    - "yes" - світло є
    - "no" - повна година без світла
    - "first" - перші 30 хв без світла
    - "second" - другі 30 хв без світла
    """
    soup = BeautifulSoup(html, 'html.parser')
    slots = {str(i): "yes" for i in range(1, 25)}
    slot_elements = soup.select('div.bz-schedule-slot')

    for el in slot_elements:
        is_off = 'bz-schedule-slot--off' in el.get('class', [])
        if not is_off:
            continue

        ts = el.select_one('.bz-schedule-slot__time')
        if not ts:
            continue

        t = parse_time_slot(ts.get_text(strip=True))
        if not t:
            continue

        start_hour, start_minute, end_hour, end_minute = t

        # Стартовий слот
        start_slot = hour_to_slot(start_hour)

        # Обробка кінця з округленням
        rounded_end_minute = round_minutes_to_half_hour(end_minute)
        if rounded_end_minute == 30:
            actual_end_hour = end_hour + 1
        else:
            actual_end_hour = end_hour
        end_slot = hour_to_slot(actual_end_hour)

        # Заповнюємо всі слоти як "no"
        for slot in range(start_slot, end_slot):
            if 1 <= slot <= 24:
                slots[str(slot)] = "no"

        # Коригуємо перший слот, якщо старт не з 00 хв
        if start_minute != 0 and start_slot <= 24:
            if start_minute >= 30:
                slots[str(start_slot)] = "second"
            else:
                slots[str(start_slot)] = "first"

        # Коригуємо останній слот, якщо кінець не на 00 хв
        if end_minute != 0:
            last_full_hour = actual_end_hour - 1
            last_slot = hour_to_slot(last_full_hour)
            if last_slot <= 24 and not (end_hour == 23 and end_minute == 59):
                if end_minute <= 30:
                    slots[str(last_slot)] = "first"
                else:
                    slots[str(last_slot)] = "second"

    return slots

def get_queue_urls(q):
    slug = q.replace('.', '-')
    return BASE_URL.format(queue=slug), TOMORROW_URL.format(queue=slug)

def parse_queue(s, q, i):
    try:
        time.sleep(1.5)
        log(f"[{i:2d}/12] {q}")
        tu, tmu = get_queue_urls(q)
        tr, tmur = s.get(tu, timeout=30), s.get(tmu, timeout=30)
        return {
            'queue_key': q,
            'today_slots': parse_html_schedule(tr.text) if tr.ok else {},
            'tomorrow_slots': parse_html_schedule(tmur.text) if tmur.ok else {}
        }
    except Exception as e:
        log(f"[{i:2d}/12] ERROR: {e}")
        return None

def transform_to_gpv(qd, now):
    td = now.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=KYIV_TZ)
    tts, tmt = int(td.timestamp()), int((td + timedelta(days=1)).timestamp())
    data = {}
    for ts in [tts, tmt]:
        data[str(ts)] = {}
        for qk in ALL_QUEUE_KEYS:
            gpv_key = QUEUE_TO_GPV[qk]
            queue_data = next((qd2 for qd2 in qd if qd2 and qd2['queue_key'] == qk), None)
            if queue_data:
                slots = queue_data['today_slots'] if ts == tts else queue_data['tomorrow_slots']
            else:
                slots = {str(i): "yes" for i in range(1, 25)}
            data[str(ts)][gpv_key] = slots
    return data

def save_results(qd_list):
    now = datetime.now(KYIV_TZ)
    data = transform_to_gpv(qd_list, now)
    
    result = {
        "regionId": "vinnytsia",
        "lastUpdated": int(now.timestamp()),
        "fact": {
            "data": data,
            "update": now.strftime('%d.%m.%Y %H:%M'),
            "today": int(now.replace(hour=0, minute=0, second=0, tzinfo=KYIV_TZ).timestamp())
        },
        "preset": {
            "days": {
                "1": "Понеділок",
                "2": "Вівторок",
                "3": "Середа",
                "4": "Четвер",
                "5": "П'ятниця",
                "6": "Субота",
                "7": "Неділя"
            },
            "sch_names": {f"GPV{k}": f"Черга {k}" for k in QUEUE_MAPPING},
            "updateFact": now.strftime('%d.%m.%Y %H:%M')
        },
        "lastUpdateStatus": {
            "status": "parsed",
            "ok": True,
            "code": 200,
            "message": None,
            "at": int(now.timestamp()),
            "attempt": 1
        },
        "regionAffiliation": "Вінницька область",
        "meta": {
            "schemaVersion": "1.0.0",
            "contentHash": hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
        }
    }
    
    os.makedirs("data", exist_ok=True)
    with open("data/Vinnytsiaoblenerho.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    log(f"✅ SAVED: data/Vinnytsiaoblenerho.json ({len([q for q in qd_list if q])}/12)")
    return True

def main():
    log("🔌 GPV ВОЕ ВІННИЦЯ - BezSvitla Parser")
    s = create_session()
    qdata = [parse_queue(s, q, i + 1) for i, q in enumerate(ALL_QUEUE_KEYS)]
    save_results(qdata)
    log("🎉 ГОТОВО!")

if __name__ == "__main__":
    main()
