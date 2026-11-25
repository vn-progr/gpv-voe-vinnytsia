#!/usr/bin/env python3
"""
🔌 GPV VOE Вінниця - Dual-Source Parser (KolyBude API + BezSvitla HTML)
Парсить 12 черг з 2 ресурсів → data/Vinnytsiaoblenerho.json
"""
import json
import os
import sys
import re
import hashlib
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

def log(msg):
    print(msg)
    sys.stdout.flush()

QUEUE_MAPPING = {
    "1.1": "1.1", "1.2": "1.2",
    "2.1": "2.1", "2.2": "2.2",
    "3.1": "3.1", "3.2": "3.2",
    "4.1": "4.1", "4.2": "4.2",
    "5.1": "5.1", "5.2": "5.2",
    "6.1": "6.1", "6.2": "6.2"
}

QUEUE_TO_GPV = {k: f"GPV{k}" for k in QUEUE_MAPPING}
ALL_QUEUE_KEYS = list(QUEUE_MAPPING)
KYIV_TZ = timezone(timedelta(hours=2))
OUTPUT_FILE = "data/Vinnytsiaoblenerho.json"
KOLYBUDE_API_URL = "https://kolybude.com/api/status?region=vinnytsia"

def create_session():
    s = requests.Session()
    retry_strategy = Retry(
        total=3,
        backoff_factor=0.5,
        status_forcelist=[429, 500, 502, 503, 504]
    )
    adapter = HTTPAdapter(max_retries=retry_strategy, pool_connections=20, pool_maxsize=20)
    s.mount('http://', adapter)
    s.mount('https://', adapter)
    s.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/html,application/xhtml+xml,*/*;q=0.9',
        'Accept-Language': 'uk,en;q=0.9',
    })
    return s

# --- Допоміжні функції перетворення часу у слоти ---

def parse_time_slot(t):
    m = re.search(r'(\d{1,2}):(\d{2})\s*[––\-\s–]\s*(\d{1,2}):(\d{2})', t)
    return tuple(map(int, m.groups())) if m else None

def round_minutes_to_half_hour(minutes):
    return 30 if minutes >= 30 else 0

def hour_to_slot(h):
    return 1 if h == 0 else h + 1

def intervals_to_slots(time_strings):
    """Перетворює список рядків виду ['08:00-10:00', '14:00-16:00'] у слоти 1..24."""
    slots = {str(i): "yes" for i in range(1, 25)}
    for raw_t in time_strings:
        t = parse_time_slot(raw_t)
        if not t:
            continue

        start_hour, start_minute, end_hour, end_minute = t
        start_slot = hour_to_slot(start_hour)

        rounded_end_minute = round_minutes_to_half_hour(end_minute)
        actual_end_hour = end_hour + 1 if rounded_end_minute == 30 else end_hour
        end_slot = hour_to_slot(actual_end_hour)

        for slot in range(start_slot, end_slot):
            if 1 <= slot <= 24:
                slots[str(slot)] = "no"

        if start_minute != 0 and start_slot <= 24:
            slots[str(start_slot)] = "second" if start_minute >= 30 else "first"

        if end_minute != 0:
            last_full_hour = actual_end_hour - 1
            last_slot = hour_to_slot(last_full_hour)
            if last_slot <= 24 and not (end_hour == 23 and end_minute == 59):
                slots[str(last_slot)] = "first" if end_minute <= 30 else "second"

    return slots

def has_outages(slots):
    return bool(slots) and any(v != "yes" for v in slots.values())

# --- Парсери для KolyBude API та BezSvitla HTML ---

def fetch_kolybude_all(s, expected_today_str, expected_tomorrow_str):
    """Один JSON-запит на всі 12 черг з kolybude.com/api/status."""
    empty_map = {q: {'today': None, 'tomorrow': None} for q in ALL_QUEUE_KEYS}
    try:
        r = s.get(KOLYBUDE_API_URL, timeout=20)
        if not r.ok:
            log(f"  [kolybude] HTTP {r.status_code}")
            return empty_map

        payload = r.json()
        published = payload.get("published", {})
        schedules = payload.get("schedules", {})
        api_today = payload.get("todayDate")
        api_tomorrow = payload.get("tomorrowDate")

        today_valid = bool(published.get("today")) and (not api_today or api_today == expected_today_str)
        tomorrow_valid = bool(published.get("tomorrow")) and (not api_tomorrow or api_tomorrow == expected_tomorrow_str)

        log(f"  [kolybude] API OK | today={api_today} (pub={published.get('today')}) | tomorrow={api_tomorrow} (pub={published.get('tomorrow')})")

        result = {}
        for q in ALL_QUEUE_KEYS:
            q_sched = schedules.get(q, {})
            today_slots = None
            tomorrow_slots = None

            if today_valid and "today" in q_sched:
                raw_pairs = q_sched["today"] or []
                intervals = [f"{pair[0]}-{pair[1]}" for pair in raw_pairs if len(pair) == 2]
                today_slots = intervals_to_slots(intervals)

            if tomorrow_valid and "tomorrow" in q_sched:
                raw_pairs = q_sched["tomorrow"] or []
                intervals = [f"{pair[0]}-{pair[1]}" for pair in raw_pairs if len(pair) == 2]
                tomorrow_slots = intervals_to_slots(intervals)

            result[q] = {'today': today_slots, 'tomorrow': tomorrow_slots}

        return result
    except Exception as e:
        log(f"  [kolybude] API error: {e}")
        return empty_map

def parse_bezsvitla_html(html):
    soup = BeautifulSoup(html, 'html.parser')
    intervals = []
    for el in soup.select('div.bz-schedule-slot.bz-schedule-slot--off'):
        ts = el.select_one('.bz-schedule-slot__time')
        if ts:
            intervals.append(ts.get_text(strip=True))
    return intervals_to_slots(intervals)

def fetch_bezsvitla(s, q):
    slug = q.replace('.', '-')
    u_today = f"https://bezsvitla.com.ua/vinnytska-oblast/cherha-{slug}"
    u_tomorrow = f"{u_today}/grafik-na-zavtra"
    try:
        r1 = s.get(u_today, timeout=20)
        r2 = s.get(u_tomorrow, timeout=20)
        return {
            'today': parse_bezsvitla_html(r1.text) if r1.ok else None,
            'tomorrow': parse_bezsvitla_html(r2.text) if r2.ok else None,
        }
    except Exception as e:
        log(f"  [bezsvitla] {q} error: {e}")
        return {'today': None, 'tomorrow': None}

# --- Логіка вибору найсвіжішого джерела ---

def load_previous_data():
    if not os.path.exists(OUTPUT_FILE):
        return {}
    try:
        with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
        return raw.get("fact", {}).get("data", {})
    except Exception:
        return {}

def pick_best_slots(sources_slots, prev_slots):
    """
    1. Шукає джерело з непорожніми даними, які відрізняються від попереднього збереження.
    2. Якщо змін немає — повертає перше джерело з непорожніми даними.
    3. Якщо на обох джерелах порожньо — повертає порожній графік (усі 'yes').
    """
    valid_sources = {name: sl for name, sl in sources_slots.items() if sl is not None}
    non_empty = {name: sl for name, sl in valid_sources.items() if has_outages(sl)}

    if non_empty:
        if prev_slots:
            for name, sl in non_empty.items():
                if sl != prev_slots:
                    return sl, name
        first_name = next(iter(non_empty))
        return non_empty[first_name], first_name

    if valid_sources:
        first_name = next(iter(valid_sources))
        return valid_sources[first_name], f"{first_name} (empty)"

    return {str(i): "yes" for i in range(1, 25)}, "fallback"

def process_queue(s, q, r_kol, prev_today, prev_tomorrow):
    r_bez = fetch_bezsvitla(s, q)

    today_candidates = {
        'kolybude': r_kol['today'],
        'bezsvitla': r_bez['today'],
    }
    tomorrow_candidates = {
        'kolybude': r_kol['tomorrow'],
        'bezsvitla': r_bez['tomorrow'],
    }

    best_today, src_today = pick_best_slots(today_candidates, prev_today)
    best_tomorrow, src_tomorrow = pick_best_slots(tomorrow_candidates, prev_tomorrow)

    log(f"Черга {q:3s} | Сьогодні: {src_today:18s} | Завтра: {src_tomorrow}")
    return {
        'queue_key': q,
        'today_slots': best_today,
        'tomorrow_slots': best_tomorrow
    }

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
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    log(f"✅ SAVED: {OUTPUT_FILE} ({len([q for q in qd_list if q])}/12)")
    return True

def main():
    log("🔌 GPV ВОЕ ВІННИЦЯ - Dual-Source Parser (KolyBude API + BezSvitla)")
    now = datetime.now(KYIV_TZ)
    td = now.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=KYIV_TZ)
    tmt_dt = td + timedelta(days=1)

    tts_str = str(int(td.timestamp()))
    tmt_str = str(int(tmt_dt.timestamp()))
    today_date_str = td.strftime('%Y-%m-%d')
    tomorrow_date_str = tmt_dt.strftime('%Y-%m-%d')

    prev_data = load_previous_data()
    s = create_session()

    kolybude_all = fetch_kolybude_all(s, today_date_str, tomorrow_date_str)

    qdata = []
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = []
        for q in ALL_QUEUE_KEYS:
            gpv_key = QUEUE_TO_GPV[q]
            prev_today = prev_data.get(tts_str, {}).get(gpv_key)
            prev_tomorrow = prev_data.get(tmt_str, {}).get(gpv_key)
            futures.append(
                executor.submit(process_queue, s, q, kolybude_all[q], prev_today, prev_tomorrow)
            )

        for f in futures:
            qdata.append(f.result())

    save_results(qdata)
    log("🎉 ГОТОВО!")

if __name__ == "__main__":
    main()
