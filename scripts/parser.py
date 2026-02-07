#!/usr/bin/env python3
"""
🔌 GPV VOE Вінниця - BezSvitla Parser
Парсить 12 черг → data/Vinnytsiaoblenerho.json (GPV формат)
"""
import json, os, time, sys, re
from datetime import datetime, timezone, timedelta
import hashlib
from bs4 import BeautifulSoup
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

def log(msg): print(msg); sys.stdout.flush()

for lib in ['requests', 'bs4']:
    try: __import__(lib)
    except ImportError:
        print(f"❌ ERROR: pip install -r requirements.txt"); sys.exit(1)

QUEUE_MAPPING = {"1.1":"1.1","1.2":"1.2","2.1":"2.1","2.2":"2.2","3.1":"3.1","3.2":"3.2","4.1":"4.1","4.2":"4.2","5.1":"5.1","5.2":"5.2","6.1":"6.1","6.2":"6.2"}
QUEUE_TO_GPV = {k:f"GPV{k}" for k in QUEUE_MAPPING}
ALL_QUEUE_KEYS = list(QUEUE_MAPPING)
BASE_URL = "https://bezsvitla.com.ua/vinnytska-oblast/cherha-{queue}"
TOMORROW_URL = BASE_URL + "/grafik-na-zavtra"
KYIV_TZ = timezone(timedelta(hours=2))

def create_session():
    s = requests.Session()
    s.mount('http://', HTTPAdapter(max_retries=Retry(total=3,backoff_factor=1)))
    s.mount('https://', HTTPAdapter(max_retries=Retry(total=3,backoff_factor=1)))
    s.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'text/html,application/xhtml+xml,*/*;q=0.9',
        'Accept-Language': 'uk,en;q=0.9',
    })
    return s

def parse_time_slot(t): 
    m = re.match(r'(\d{2}):(\d{2})\s*[––\-\s–]\s*(\d{2}):(\d{2})', t)
    return tuple(map(int, m.groups())) if m else None

def parse_html_schedule(html):
    soup = BeautifulSoup(html, 'html.parser')
    slots, li_el = {}, soup.select('div.card-body ul li')
    for li in li_el:
        ts = li.find('span'); icon = li.select_one('.icon-off, .icon-on')
        if ts and icon:
            t = parse_time_slot(ts.get_text(strip=True))
            if t:
                sh,sm,eh,em = t; is_off = bool(li.select_one('.icon-off'))
                for slot in range(hour_to_slot(sh), hour_to_slot(eh)):
                    if 1<=slot<=24: slots[str(slot)] = "no" if is_off else "yes"
    return {str(i):slots.get(str(i),"yes") for i in range(1,25)}

def hour_to_slot(h): return 1 if h==0 else h+1

def get_queue_urls(q): 
    slug = q.replace('.','-')
    return BASE_URL.format(queue=slug), TOMORROW_URL.format(queue=slug)

def parse_queue(s, q, i):
    try:
        time.sleep(1.5)
        log(f"[{i:2d}/12] {q}")
        tu, tmu = get_queue_urls(q)
        tr, tmur = s.get(tu,timeout=30), s.get(tmu,timeout=30)
        return {
            'queue_key': q,
            'today_slots': parse_html_schedule(tr.text) if tr.ok else {},
            'tomorrow_slots': parse_html_schedule(tmur.text) if tmur.ok else {}
        }
    except: return None

def transform_to_gpv(qd, now):
    td = now.replace(hour=0,minute=0,second=0,microsecond=0,tzinfo=KYIV_TZ)
    tts, tmt = int(td.timestamp()), int((td+timedelta(days=1)).timestamp())
    data = {}
    for ts in [tts,tmt]:
        data[str(ts)] = {QUEUE_TO_GPV[qk]: next((qd2['today_slots'] if ts==tts else qd2['tomorrow_slots'] 
            for qd2 in qd if qd2 and qd2['queue_key']==qk), {}) for qk in ALL_QUEUE_KEYS}
    return data

def save_results(qd_list):
    now = datetime.now(KYIV_TZ)
    data = transform_to_gpv(qd_list, now)
    result = {
        "regionId": "vinnytsia", "lastUpdated": int(now.timestamp()),
        "fact": {"data": data, "update": now.strftime('%d.%m.%Y %H:%M'), 
                "today": int(now.replace(hour=0,minute=0,second=0,tzinfo=KYIV_TZ).timestamp())},
        "preset": {"days": {str(i):["","Понеділок","Вівторок","Середа","Четвер","П'ятниця","Субота","Неділя"][i] for i in range(8)},
                  "sch_names": {f"GPV{k}": f"Черга {k}" for k in QUEUE_MAPPING},
                  "updateFact": now.strftime('%d.%m.%Y %H:%M')},
        "lastUpdateStatus": {"status": "parsed", "ok": True, "code": 200, "at": int(now.timestamp())},
        "regionAffiliation": "Вінницька область",
        "meta": {"schemaVersion": "1.0.0", "contentHash": hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest()}
    }
    os.makedirs("data", exist_ok=True)
    with open("data/Vinnytsiaoblenerho.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    log(f"✅ SAVED: data/Vinnytsiaoblenerho.json ({len([q for q in qd_list if q])}/12)")
    return True

def main():
    log("🔌 GPV ВОЕ ВІННИЦЯ - BezSvitla Parser")
    s = create_session()
    qdata = [parse_queue(s, q, i+1) for i,q in enumerate(ALL_QUEUE_KEYS)]
    save_results(qdata)
    log("🎉 ГОТОВО!")

if __name__ == "__main__": main()
