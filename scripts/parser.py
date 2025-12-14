#!/usr/bin/env python3
"""
E-svitlo Parser - витягує дані про плановані відключення
Для 12 черг Вінниця регіон (6 груп по 2 черги)
EIC значення прикриті через GitHub Secrets
Трансформує дані в формат GPV
Залишає тільки сьогодні та завтра
"""
import json
import os
import time
import sys
from datetime import datetime, timezone, timedelta
import hashlib

def log(msg):
    print(msg)
    sys.stdout.flush()

try:
    import cloudscraper
    log("OK: cloudscraper")
except ImportError:
    log("ERROR: cloudscraper not installed")
    exit(1)

# 12 черг Вінниця (6 груп по 2 черги)
QUEUE_MAPPING = {
    "1.1": "queue 1.1",
    "1.2": "queue 1.2",
    "2.1": "queue 2.1",
    "2.2": "queue 2.2",
    "3.1": "queue 3.1",
    "3.2": "queue 3.2",
    "4.1": "queue 4.1",
    "4.2": "queue 4.2",
    "5.1": "queue 5.1",
    "5.2": "queue 5.2",
    "6.1": "queue 6.1",
    "6.2": "queue 6.2"
}

QUEUE_TO_GPV = {
    "1.1": "GPV1.1",
    "1.2": "GPV1.2",
    "2.1": "GPV2.1",
    "2.2": "GPV2.2",
    "3.1": "GPV3.1",
    "3.2": "GPV3.2",
    "4.1": "GPV4.1",
    "4.2": "GPV4.2",
    "5.1": "GPV5.1",
    "5.2": "GPV5.2",
    "6.1": "GPV6.1",
    "6.2": "GPV6.2"
}

ALL_QUEUE_KEYS = ["1.1", "1.2", "2.1", "2.2", "3.1", "3.2", "4.1", "4.2", "5.1", "5.2", "6.1", "6.2"]

# EIC значення з GitHub Secrets (прикриті)
EICS = {
    "1.1": os.getenv("ESVITLO_EIC_1_1"),
    "1.2": os.getenv("ESVITLO_EIC_1_2"),
    "2.1": os.getenv("ESVITLO_EIC_2_1"),
    "2.2": os.getenv("ESVITLO_EIC_2_2"),
    "3.1": os.getenv("ESVITLO_EIC_3_1"),
    "3.2": os.getenv("ESVITLO_EIC_3_2"),
    "4.1": os.getenv("ESVITLO_EIC_4_1"),
    "4.2": os.getenv("ESVITLO_EIC_4_2"),
    "5.1": os.getenv("ESVITLO_EIC_5_1"),
    "5.2": os.getenv("ESVITLO_EIC_5_2"),
    "6.1": os.getenv("ESVITLO_EIC_6_1"),
    "6.2": os.getenv("ESVITLO_EIC_6_2"),
}

# Перевірити що всі EIC задані
missing_eics = [k for k, v in EICS.items() if not v]
if missing_eics:
    log("ERROR: Missing EIC secrets: " + str(missing_eics))
    exit(1)

# Побудувати QUEUE_URLS з прикритими EIC
QUEUE_URLS = [
    f"https://vn.e-svitlo.com.ua/account_household/show_only_disconnections?eic={EICS['1.1']}&type_user=1&a=290637",
    f"https://vn.e-svitlo.com.ua/account_household/show_only_disconnections?eic={EICS['1.2']}&type_user=1&a=290637",
    f"https://vn.e-svitlo.com.ua/account_household/show_only_disconnections?eic={EICS['2.1']}&type_user=1&a=290637",
    f"https://vn.e-svitlo.com.ua/account_household/show_only_disconnections?eic={EICS['2.2']}&type_user=1&a=290637",
    f"https://vn.e-svitlo.com.ua/account_household/show_only_disconnections?eic={EICS['3.1']}&type_user=1&a=290637",
    f"https://vn.e-svitlo.com.ua/account_household/show_only_disconnections?eic={EICS['3.2']}&type_user=1&a=290637",
    f"https://vn.e-svitlo.com.ua/account_household/show_only_disconnections?eic={EICS['4.1']}&type_user=1&a=290637",
    f"https://vn.e-svitlo.com.ua/account_household/show_only_disconnections?eic={EICS['4.2']}&type_user=1&a=290637",
    f"https://vn.e-svitlo.com.ua/account_household/show_only_disconnections?eic={EICS['5.1']}&type_user=1&a=290637",
    f"https://vn.e-svitlo.com.ua/account_household/show_only_disconnections?eic={EICS['5.2']}&type_user=1&a=290637",
    f"https://vn.e-svitlo.com.ua/account_household/show_only_disconnections?eic={EICS['6.1']}&type_user=1&a=290637",
    f"https://vn.e-svitlo.com.ua/account_household/show_only_disconnections?eic={EICS['6.2']}&type_user=1&a=290637",
]

LOGIN = os.getenv("ESVITLO_LOGIN")
PASSWORD = os.getenv("ESVITLO_PASSWORD")

log("LOGIN: " + str(bool(LOGIN)))
log("PASSWORD: " + str(bool(PASSWORD)))
log("EICs loaded: " + str(len([v for v in EICS.values() if v])) + "/12")

if not LOGIN or not PASSWORD:
    log("ERROR: No credentials provided")
    exit(1)

# Kyiv timezone (UTC+2 in winter, UTC+3 in summer)
KYIV_TZ = timezone(timedelta(hours=2))

def create_scraper():
    """Створити scraper з anti-Cloudflare headers"""
    scraper = cloudscraper.create_scraper()
    scraper.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'application/json',
        'Accept-Language': 'uk,ru;q=0.9,en-US;q=0.8,en;q=0.7',
    })
    return scraper

def login(scraper):
    """Залогінитися на e-svitlo.com.ua"""
    log("[LOGIN] Starting authentication")
    
    try:
        cf = scraper.get("https://vn.e-svitlo.com.ua/", timeout=30)
        log("[LOGIN] CF challenge: " + str(cf.status_code))
    except Exception as e:
        log("[LOGIN] CF error: " + str(e))
    
    time.sleep(1)
    
    data = {
        "email": LOGIN,
        "password": PASSWORD,
    }
    
    headers = {
        "Origin": "https://vn.e-svitlo.com.ua",
        "Referer": "https://vn.e-svitlo.com.ua/user_register",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    
    resp = scraper.post(
        "https://vn.e-svitlo.com.ua/registr_all_user/login_all_user",
        data=data,
        headers=headers,
        allow_redirects=True,
        timeout=30,
    )
    
    log("[LOGIN] Response: " + str(resp.status_code))
    log("[LOGIN] URL: " + resp.url)
    
    is_logged_in = "Вихід" in resp.text or "logout" in resp.text.lower()
    log("[LOGIN] Authenticated: " + str(is_logged_in))
    
    time.sleep(2)
    return scraper

def activate_session(scraper):
    """Активувати сесію перед парсингом черг"""
    log("[SESSION] Activating session")
    try:
        cabinet_response = scraper.get("https://vn.e-svitlo.com.ua/account_household", timeout=30, allow_redirects=True)
        log("[SESSION] Cabinet status: " + str(cabinet_response.status_code))
        
        cookies_dict = scraper.cookies.get_dict()
        log("[SESSION] Cookies: " + str(len(cookies_dict)))
        
        time.sleep(1)
    except Exception as e:
        log("[SESSION] Error: " + str(e))

def get_queue_name(queue_key):
    """Отримати назву черги за ключем"""
    return QUEUE_MAPPING.get(queue_key, "unknown")

def parse_queue(scraper, url, queue_key, queue_idx):
    """Парсити одну чергу"""
    try:
        time.sleep(1)
        
        queue_name = get_queue_name(queue_key)
        
        log("[Q" + str(queue_idx) + "] " + queue_name + " Fetching...")
        
        response = scraper.get(url, timeout=30, allow_redirects=True)
        
        log("[Q" + str(queue_idx) + "] Status: " + str(response.status_code))
        
        if response.status_code != 200:
            log("[Q" + str(queue_idx) + "] ERROR: Status " + str(response.status_code))
            return []
        
        try:
            data = json.loads(response.text)
        except json.JSONDecodeError as e:
            log("[Q" + str(queue_idx) + "] JSON decode error: " + str(e))
            return []
        
        planned_list = data.get('planned_list_cab', [])
        log("[Q" + str(queue_idx) + "] Found: " + str(len(planned_list)) + " outages")
        
        outages = []
        for item in planned_list:
            if isinstance(item, dict):
                if item.get('accidentid', -1) != 0:
                    continue
                outages.append({
                    'queue': queue_name,
                    'queue_key': queue_key,
                    'acc_begin': item.get('acc_begin', ''),
                    'accend_plan': item.get('accend_plan', ''),
                    'typeid': item.get('typeid', '')
                })
        
        log("[Q" + str(queue_idx) + "] Parsed: " + str(len(outages)) + " records")
        return outages
        
    except Exception as e:
        log("[Q" + str(queue_idx) + "] EXCEPTION: " + str(e)[:100])
        return []

def round_minutes_to_half_hour(minutes):
    """Округлює хвилини до половини години
    
    < 30 хвилин → 0 (XX:00)
    >= 30 хвилин → 30 (XX:30)
    """
    return 30 if minutes >= 30 else 0

def hour_to_slot(hour):
    """Конвертує годину в номер часового слота (1-24)
    
    Слот N охоплює годину від (N-1):00 до N:00
    Приклад: слот 7 = 6:00-7:00, слот 1 = 0:00-1:00
    """
    if hour == 0:
        return 1
    else:
        return hour + 1

def create_empty_slots():
    """Створює порожні слоти (всі = yes)"""
    return {str(i): "yes" for i in range(1, 25)}

def transform_to_gpv(all_outages, kyiv_now):
    """Трансформує дані в GPV формат
    
    Залишає ТІЛЬКИ сьогодні та завтра
    Округлює хвилини до половини години для розрахунку слотів
    """
    log("[TRANSFORM] Starting transformation to GPV format")
    
    # Отримуємо сьогодні та завтра як Unix timestamps (в Kyiv timezone)
    today_date = kyiv_now.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=KYIV_TZ)
    tomorrow_date = today_date + timedelta(days=1)
    
    today_ts = int(today_date.timestamp())
    tomorrow_ts = int(tomorrow_date.timestamp())
    
    log(f"[TRANSFORM] Today: {today_ts} ({today_date}), Tomorrow: {tomorrow_ts} ({tomorrow_date})")
    
    # Групуємо вимкнення за датою та чергою
    outages_by_date_queue = {}
    
    for outage in all_outages:
        try:
            begin_str = outage['acc_begin']
            end_str = outage['accend_plan']
            
            # Парсимо ISO datetime
            # КРИТИЧНО: дані без таймзони, припускаємо Kyiv timezone
            begin_dt = datetime.fromisoformat(begin_str).replace(tzinfo=KYIV_TZ)
            end_dt = datetime.fromisoformat(end_str).replace(tzinfo=KYIV_TZ)
            
            # Отримуємо дату як Unix timestamp
            date_only = begin_dt.replace(hour=0, minute=0, second=0, microsecond=0)
            unix_ts = int(date_only.timestamp())
            
            log(f"[TRANSFORM] Outage: {begin_str} → Date TS: {unix_ts}")
            
            # ФІЛЬТРУЄМО: залишаємо тільки сьогодні та завтра
            if unix_ts not in [today_ts, tomorrow_ts]:
                log(f"[TRANSFORM] Skipping outage from {unix_ts} (not today or tomorrow)")
                continue
            
            if unix_ts not in outages_by_date_queue:
                outages_by_date_queue[unix_ts] = {}
            
            queue_key = outage['queue_key']
            
            if queue_key not in outages_by_date_queue[unix_ts]:
                outages_by_date_queue[unix_ts][queue_key] = []
            
            outages_by_date_queue[unix_ts][queue_key].append({
                'start_hour': begin_dt.hour,
                'start_minute': begin_dt.minute,
                'end_hour': end_dt.hour,
                'end_minute': end_dt.minute,
            })
            
            log(f"[TRANSFORM] Parsed: {begin_dt.hour:02d}:{begin_dt.minute:02d} - {end_dt.hour:02d}:{end_dt.minute:02d}")
            
        except Exception as e:
            log("[TRANSFORM] Error processing outage: " + str(e))
    
    # Збудуємо структуру з гарантією сьогодні + завтра
    fact_data = {}
    
    for unix_ts in [today_ts, tomorrow_ts]:
        fact_data[str(unix_ts)] = {}
        
        for queue_key in ALL_QUEUE_KEYS:
            gpv_key = QUEUE_TO_GPV.get(queue_key)
            
            # Ініціалізуємо всі слоти як "yes"
            slots = create_empty_slots()
            
            # Якщо є вимкнення для цієї черги в цей день
            if unix_ts in outages_by_date_queue and queue_key in outages_by_date_queue[unix_ts]:
                for outage in outages_by_date_queue[unix_ts][queue_key]:
                    start_hour = outage['start_hour']
                    start_minute = outage['start_minute']
                    end_hour = outage['end_hour']
                    end_minute = outage['end_minute']
                    
                    # Конвертуємо години в слоти
                    start_slot = hour_to_slot(start_hour)
                    
                    # Округлюємо кінцеві хвилини
                    rounded_end_minute = round_minutes_to_half_hour(end_minute)
                    
                    # Якщо після округлення = 30, вимкнення йде до наступної години
                    if rounded_end_minute == 30:
                        actual_end_hour = end_hour + 1
                    else:
                        actual_end_hour = end_hour
                    
                    end_slot = hour_to_slot(actual_end_hour)
                    
                    log(f"[TRANSFORM] {gpv_key} ({unix_ts}): {start_hour:02d}:{start_minute:02d}-{end_hour:02d}:{end_minute:02d} → слоти {start_slot}-{end_slot-1}")
                    
                    # Заповнюємо слоти з "no"
                    for slot in range(start_slot, end_slot):
                        if slot <= 24:
                            slots[str(slot)] = "no"
                    
                    # Логіка first/second
                    # 'second': якщо acc_begin має дробову частину (start_minute ≠ 0)
                    if start_minute != 0 and start_slot <= 24:
                        slots[str(start_slot)] = "second"
                    
                    # 'first': якщо accend_plan має дробову частину (end_minute ≠ 0)
                    # НЕ враховуємо 23:59:59 (кінець дня)
                    if end_minute != 0 and end_slot - 1 <= 24:
                        if not (end_hour == 23 and end_minute == 59):
                            slots[str(end_slot - 1)] = "first"
            
            fact_data[str(unix_ts)][gpv_key] = slots
    
    return fact_data

def calculate_hash(data_str):
    """Розраховує SHA256 хеш даних"""
    return hashlib.sha256(data_str.encode()).hexdigest()

def save_results(all_outages):
    """Зберегти результати у JSON GPV формат"""
    log("[SAVE] Transforming and writing GPV format")
    
    # Отримати поточний час у Kyiv timezone
    kyiv_now = datetime.now(KYIV_TZ)
    
    # -----------------------------------------------------------
    # ВИКОРИСТОВУЄМО UNIX TIMESTAMP (Integer)
    # -----------------------------------------------------------
    last_updated_ts = int(kyiv_now.timestamp())
    
    # Текстова дата оновлення для відображення людям (залишається по Києву)
    update_fact_str = kyiv_now.strftime('%d.%m.%Y %H:%M')
    
    # Трансформуємо дані
    fact_data = transform_to_gpv(all_outages, kyiv_now)
    
    # Отримуємо сьогоднішню дату як Unix timestamp
    today_date = kyiv_now.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=KYIV_TZ)
    today_ts = int(today_date.timestamp())
    
    # Створюємо структуру
    result = {
        "regionId": "vinnytsia",
        "lastUpdated": last_updated_ts,
        "fact": {
            "data": fact_data,
            "update": update_fact_str,
            "today": today_ts
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
            "sch_names": {
                "GPV1.1": "Черга 1.1",
                "GPV1.2": "Черга 1.2",
                "GPV2.1": "Черга 2.1",
                "GPV2.2": "Черга 2.2",
                "GPV3.1": "Черга 3.1",
                "GPV3.2": "Черга 3.2",
                "GPV4.1": "Черга 4.1",
                "GPV4.2": "Черга 4.2",
                "GPV5.1": "Черга 5.1",
                "GPV5.2": "Черга 5.2",
                "GPV6.1": "Черга 6.1",
                "GPV6.2": "Черга 6.2"
            },
            "updateFact": update_fact_str
        },
        "lastUpdateStatus": {
            "status": "parsed",
            "ok": True,
            "code": 200,
            "message": None,
            "at": last_updated_ts,
            "attempt": 1
        },
        "regionAffiliation": "Вінницька область"
    }
    
    # Розраховуємо хеш контенту (факт даних)
    fact_data_str = json.dumps(result['fact']['data'], sort_keys=True, ensure_ascii=False)
    content_hash = calculate_hash(fact_data_str)
    
    # Додаємо мета інформацію
    result["meta"] = {
        "schemaVersion": "1.0.0",
        "contentHash": content_hash
    }
    
    # Створити папку data якщо не існує
    data_dir = "data"
    if not os.path.exists(data_dir):
        os.makedirs(data_dir)
        log("[SAVE] Created directory: " + data_dir)
    
    # Записати файл у папку data
    file_path = os.path.join(data_dir, "Vinnytsiaoblenerho.json")
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    log("[SAVE] Success: Saved to " + file_path)
    log(f"[SAVE] Total dates: {len(fact_data)}, Queues per date: {len(ALL_QUEUE_KEYS)}, Content hash: {content_hash}")

def main():
    log("=" * 70)
    log("E-SVITLO PARSER - START")
    log("=" * 70)
    
    scraper = create_scraper()
    login(scraper)
    activate_session(scraper)
    
    log("[MAIN] Parsing 12 queues...")
    all_outages = []
    
    for idx, (queue_key, url) in enumerate(zip(ALL_QUEUE_KEYS, QUEUE_URLS), 1):
        queue_outages = parse_queue(scraper, url, queue_key, idx)
        all_outages.extend(queue_outages)
    
    log("[MAIN] Total outages: " + str(len(all_outages)))
    save_results(all_outages)
    
    log("=" * 70)
    log("DONE")
    log("=" * 70)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log("[MAIN] FATAL ERROR: " + str(e))
        import traceback
        traceback.print_exc()
        exit(1)
