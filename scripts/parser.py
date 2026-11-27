#!/usr/bin/env python3
"""
🔌 GPV VOE Вінниця - Dual-Source Parser (BezSvitla + KolyBude API)
Одночасно опитує bezsvitla.com.ua та https://kolybude.com/api/status?region=vinnytsia,
зберігає кеш джерел у data/sources_cache.json, а чистий графік → data/Vinnytsiaoblenerho.json
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
SOURCES_CACHE_FILE = "data/sources_cache.json"
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
        'Accept': 'application/json,text/html,application/xhtml+xml,*/*;q=0.9',
        'Accept-Language': 'uk,en;q=0.9',
        'Cache-Control': 'no-cache, no-store, must-revalidate',
        'Pragma': 'no-cache',
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
    """Перетворює список рядків виду ['08:00-10:00', '22:00-24:00'] у слоти 1..24."""
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


def pairs_to_slots(interval_pairs):
    """Перетворює масив пар [['00:00', '03:30'], ['22:00', '24:00']] з KolyBude API у слоти 1..24."""
    time_strings = [f"{pair[0]}-{pair[1]}" for pair in interval_pairs if isinstance(pair, (list, tuple)) and len(pair) >= 2]
    return intervals_to_slots(time_strings)


def has_outages(slots):
    return bool(slots) and any(v != "yes" for v in slots.values())


# --- Парсери для BezSvitla (HTML по чергах) та KolyBude (єдиний JSON API) ---

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


def fetch_kolybude_all(s, expected_today_str, expected_tomorrow_str):
    """
    Отримує одним запитом https://kolybude.com/api/status?region=vinnytsia
    графіки для всіх 12 черг і зіставляє їх за датами todayDate / tomorrowDate.
    """
    empty_res = {q: {'today': None, 'tomorrow': None} for q in ALL_QUEUE_KEYS}
    try:
        r = s.get(KOLYBUDE_API_URL, timeout=20)
        if not r.ok:
            log(f"  [kolybude] HTTP {r.status_code}")
            return empty_res

        payload = r.json()
        api_today = payload.get("todayDate")
        api_tomorrow = payload.get("tomorrowDate")
        published = payload.get("published", {})
        schedules = payload.get("schedules", {})

        log(f"  [kolybude] API OK: today={api_today} (pub={published.get('today')}), tomorrow={api_tomorrow} (pub={published.get('tomorrow')})")

        res = {}
        for q in ALL_QUEUE_KEYS:
            q_sched = schedules.get(q, {})
            q_out = {'today': None, 'tomorrow': None}

            for api_day_key, api_date_val in [('today', api_today), ('tomorrow', api_tomorrow)]:
                if not api_date_val:
                    continue
                if api_date_val == expected_today_str:
                    target_key = 'today'
                elif api_date_val == expected_tomorrow_str:
                    target_key = 'tomorrow'
                else:
                    continue

                if published.get(api_day_key) is False:
                    q_out[target_key] = {str(i): "yes" for i in range(1, 25)}
                elif api_day_key in q_sched and isinstance(q_sched[api_day_key], list):
                    q_out[target_key] = pairs_to_slots(q_sched[api_day_key])

            res[q] = q_out

        return res
    except Exception as e:
        log(f"  [kolybude] API error: {e}")
        return empty_res


# --- Завантаження та збереження станів (окремо JSON і кеш джерел) ---

def load_previous_data():
    if not os.path.exists(OUTPUT_FILE):
        return {}
    try:
        with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
        return raw.get("fact", {}).get("data", {})
    except Exception:
        return {}


def load_sources_cache():
    if not os.path.exists(SOURCES_CACHE_FILE):
        return {}
    try:
        with open(SOURCES_CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_sources_cache(cache):
    os.makedirs("data", exist_ok=True)
    with open(SOURCES_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2, sort_keys=True)


def pick_best_slots(sources_slots, prev_merged_slots, prev_per_source):
    """
    Зіставляє два джерела з їхніми попередніми станами із data/sources_cache.json:
    1. Якщо обидва джерела доступні, мають відключення і ЗБІГАЮТЬСЯ між собою — це 100% актуальний графік.
    2. Якщо одне з джерел оновилося відносно свого попереднього стану (або з'явилося вперше для цієї дати)
       і відрізняється від поточного JSON — беремо його.
    3. Інакше утримуємо поточний збережений графік (prev_merged_slots), щоб застарілий сайт не відкотив зміни.
    """
    valid_sources = {name: sl for name, sl in sources_slots.items() if sl is not None}
    non_empty = {name: sl for name, sl in valid_sources.items() if has_outages(sl)}

    # 1. Якщо кілька джерел дають відключення і вони ідентичні — сайти синхронізовані, беремо їх
    if len(non_empty) >= 2:
        unique_schedules = list(non_empty.values())
        if all(sl == unique_schedules[0] for sl in unique_schedules[1:]):
            names_label = "+".join(non_empty.keys())
            status = "synced" if unique_schedules[0] != prev_merged_slots else "ok"
            return unique_schedules[0], f"{names_label} ({status})"

    # 2. Перевіряємо, чи якесь із джерел оновилося відносно САМОГО СЕБЕ (або з'явилося вперше для цієї дати)
    changed_non_empty = []
    for name, sl in non_empty.items():
        old_src_sl = prev_per_source.get(name)
        if old_src_sl is None or sl != old_src_sl:
            changed_non_empty.append((name, sl))

    if changed_non_empty:
        for name, sl in changed_non_empty:
            if sl != prev_merged_slots:
                return sl, f"{name} (updated)"
        name, sl = changed_non_empty[0]
        return sl, f"{name} (synced)"

    # 3. Якщо жодне джерело не змінилося відносно себе, але вже є збережений непорожній графік — тримаємо його
    if prev_merged_slots and has_outages(prev_merged_slots):
        if valid_sources and not non_empty and all(
            prev_per_source.get(name) is not None and valid_sources[name] != prev_per_source[name]
            for name in valid_sources
        ):
            first_name = next(iter(valid_sources))
            return valid_sources[first_name], f"{first_name} (cleared)"

        matching = [name for name, sl in non_empty.items() if sl == prev_merged_slots]
        src_label = "+".join(matching) if matching else "cached"
        return prev_merged_slots, src_label

    # 4. Перший запуск або досі не було відключень: беремо перше непорожнє джерело
    if non_empty:
        first_name = next(iter(non_empty))
        return non_empty[first_name], first_name

    # 5. Обидва джерела порожні
    if valid_sources:
        first_name = next(iter(valid_sources))
        return valid_sources[first_name], f"{first_name} (empty)"

    return {str(i): "yes" for i in range(1, 25)}, "fallback"


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


def save_results(qd_list, now):
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
    log("🔌 GPV ВОЕ ВІННИЦЯ - Dual-Source Parser (BezSvitla + KolyBude API)")
    now = datetime.now(KYIV_TZ)
    td = now.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=KYIV_TZ)
    tm = td + timedelta(days=1)

    tts_str = str(int(td.timestamp()))
    tmt_str = str(int(tm.timestamp()))
    today_date_str = td.strftime('%Y-%m-%d')
    tomorrow_date_str = tm.strftime('%Y-%m-%d')

    prev_data = load_previous_data()
    sources_cache = load_sources_cache()

    valid_ts = {tts_str, tmt_str}
    clean_cache = {ts: val for ts, val in sources_cache.items() if ts in valid_ts}
    clean_cache.setdefault(tts_str, {})
    clean_cache.setdefault(tmt_str, {})

    s = create_session()

    # Паралельно запускаємо 1 запит до KolyBude API та 12 запитів до BezSvitla
    with ThreadPoolExecutor(max_workers=6) as executor:
        f_kol_all = executor.submit(fetch_kolybude_all, s, today_date_str, tomorrow_date_str)
        bez_futures = {q: executor.submit(fetch_bezsvitla, s, q) for q in ALL_QUEUE_KEYS}

        kol_all = f_kol_all.result()
        bez_all = {q: bez_futures[q].result() for q in ALL_QUEUE_KEYS}

    qdata = []
    for q in ALL_QUEUE_KEYS:
        gpv_key = QUEUE_TO_GPV[q]
        prev_today = prev_data.get(tts_str, {}).get(gpv_key)
        prev_tomorrow = prev_data.get(tmt_str, {}).get(gpv_key)
        cache_today_q = clean_cache[tts_str].get(gpv_key, {})
        cache_tomorrow_q = clean_cache[tmt_str].get(gpv_key, {})

        r_bez = bez_all[q]
        r_kol = kol_all[q]

        today_candidates = {
            'bezsvitla': r_bez['today'],
            'kolybude': r_kol['today'],
        }
        tomorrow_candidates = {
            'bezsvitla': r_bez['tomorrow'],
            'kolybude': r_kol['tomorrow'],
        }

        best_today, src_today = pick_best_slots(today_candidates, prev_today, cache_today_q)
        best_tomorrow, src_tomorrow = pick_best_slots(tomorrow_candidates, prev_tomorrow, cache_tomorrow_q)

        new_cache_today = dict(cache_today_q)
        for name, sl in today_candidates.items():
            if sl is not None:
                new_cache_today[name] = sl

        new_cache_tomorrow = dict(cache_tomorrow_q)
        for name, sl in tomorrow_candidates.items():
            if sl is not None:
                new_cache_tomorrow[name] = sl

        clean_cache[tts_str][gpv_key] = new_cache_today
        clean_cache[tmt_str][gpv_key] = new_cache_tomorrow

        log(f"Черга {q:3s} | Сьогодні: {src_today:24s} | Завтра: {src_tomorrow}")
        qdata.append({
            'queue_key': q,
            'today_slots': best_today,
            'tomorrow_slots': best_tomorrow,
        })

    save_sources_cache(clean_cache)
    save_results(qdata, now)
    log("🎉 ГОТОВО!")


if __name__ == "__main__":
    main()
