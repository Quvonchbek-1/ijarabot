"""
OLX.uz -> Telegram kanal boti (ijaraga kvartira e'lonlari).

Ishga tushirish:
    python main.py            # oddiy rejim (kanalga yuboradi)
    python main.py test       # DRY RUN: hech narsa yubormaydi, faqat log
    python main.py discover "kvartira ijaraga Toshkent"   # category/region/city ID larni topish

Kerakli env o'zgaruvchilar (GitHub Secrets):
    BOT_TOKEN, CHANNEL_ID, BOT_USERNAME
Ixtiyoriy:
    CATEGORY_ID, REGION_ID, CITY_ID, DISTRICT_ID, LIMIT, MAX_SEND, MIN_PRICE, MAX_PRICE
"""

import os
import re
import sys
import html
import time
import json
import logging

try:
    import cloudscraper
except ImportError:  # GitHub Actions'da requirements.txt bo'lmasa
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "cloudscraper"])
    import cloudscraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("olx_bot")

# ---------------------------------------------------------------- CONFIG ----

BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
CHANNEL_ID = os.environ.get("CHANNEL_ID", "").strip()
BOT_USERNAME = os.environ.get("BOT_USERNAME", "").strip().lstrip("@")

# OLX qidiruv parametrlari. ID larni "python main.py discover ..." bilan tekshiring.
CATEGORY_ID = os.environ.get("CATEGORY_ID", "1147").strip()   # Kvartira ijaraga (uzoq muddat)
REGION_ID = os.environ.get("REGION_ID", "5").strip()          # Toshkent shahri
CITY_ID = os.environ.get("CITY_ID", "").strip()
DISTRICT_ID = os.environ.get("DISTRICT_ID", "").strip()       # masalan Yashnobod

LIMIT = int(os.environ.get("LIMIT", "50"))
MAX_SEND = int(os.environ.get("MAX_SEND", "5"))               # bitta run'da nechta post
MIN_PRICE_USD = float(os.environ.get("MIN_PRICE", "50"))
MAX_PRICE_USD = float(os.environ.get("MAX_PRICE", "5000"))

SEEN_FILE = os.environ.get("SEEN_FILE", "seen_ids.txt")
INSTAGRAM_LINK = os.environ.get("INSTAGRAM_LINK", "toshkent_ijaraga")
TELEGRAM_CONTACT = os.environ.get("TELEGRAM_CONTACT", "@turayev_bek")
FALLBACK_PHONE = os.environ.get("FALLBACK_PHONE", "")

DRY_RUN = False  # "test" argumenti bilan yoqiladi

BASE = "https://www.olx.uz/api/v1/offers/"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "uz-UZ,uz;q=0.9,ru;q=0.8,en;q=0.7",
    "Referer": "https://www.olx.uz/",
    "Origin": "https://www.olx.uz",
}

scraper = cloudscraper.create_scraper(
    browser={"browser": "chrome", "platform": "windows", "desktop": True}
)

# --------------------------------------------------------------- FILTRLAR ---
# DIQQAT: kategoriya bo'yicha qidirilayotgani uchun "telefon/televizor/mashina"
# kabi so'zlarni qora ro'yxatga qo'yish SHART EMAS — ular tavsiflarda doim
# uchraydi ("kir yuvish mashinasi", "televizor bor") va barcha normal
# e'lonlarni rad etib yuboradi. Faqat sutkalik ijara va sotuvni filtrlaymiz.

DAILY_PATTERNS = [
    r"sutka", r"сутк", r"посуточ", r"\bkunlik\b", r"kunbay",
    r"soatlik", r"soatiga", r"\bчас(?:ов|а)?\b", r"\bночь\b", r"\bkecha(?:ga|lik)\b",
]

SALE_PATTERNS = [
    r"sotiladi", r"sotuvga", r"продаю", r"продает", r"продажа", r"срочно продам",
]

RENT_PATTERNS = [
    r"ijara", r"ijaraga", r"arenda", r"аренд", r"сда(?:ется|ю|м)", r"beriladi", r"снять",
]

NON_HOUSING_PATTERNS = [
    r"\bofis\b", r"\bофис", r"\bombor\b", r"\bсклад", r"noturar", r"нежил",
    r"\bмагазин\b", r"\bdo'kon\b", r"\bуслуг", r"\bhovli\b.*sotil",
]


def matches(patterns, text):
    for p in patterns:
        if re.search(p, text, flags=re.IGNORECASE):
            return p
    return None


# ------------------------------------------------------------------ UTILS ---

def validate_config():
    problems = []
    if not BOT_TOKEN:
        problems.append("BOT_TOKEN bo'sh.")
    if not CHANNEL_ID:
        problems.append("CHANNEL_ID bo'sh.")
    if not BOT_USERNAME:
        log.warning("BOT_USERNAME bo'sh — deep link ishlamaydi.")
    for p in problems:
        log.error(p)
    return not problems


def check_bot_access():
    try:
        res = scraper.get(
            f"https://api.telegram.org/bot{BOT_TOKEN}/getChat",
            params={"chat_id": CHANNEL_ID},
            timeout=15,
        )
        data = res.json()
        if not data.get("ok"):
            log.error("getChat xatosi: %s", data.get("description"))
            return False
        log.info("Kanal topildi: %s", data.get("result", {}).get("title", CHANNEL_ID))
        return True
    except Exception as e:
        log.error("Telegram tekshiruvida xato: %s", e)
        return False


def load_seen_ids():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            return set(line.strip() for line in f if line.strip())
    return set()


def save_seen_id(item_id):
    with open(SEEN_FILE, "a", encoding="utf-8") as f:
        f.write(f"{item_id}\n")


def api_get(url, params=None, timeout=25, tries=3):
    """OLX API'ga xavfsiz so'rov (qayta urinish bilan)."""
    for attempt in range(1, tries + 1):
        try:
            res = scraper.get(url, headers=HEADERS, params=params, timeout=timeout)
            if res.status_code == 200:
                return res.json()
            log.warning("OLX %s -> status %s (urinish %d)", url, res.status_code, attempt)
            if res.status_code in (403, 429):
                time.sleep(3 * attempt)
                continue
            return None
        except Exception as e:
            log.warning("So'rov xatosi (%d): %s", attempt, e)
            time.sleep(2 * attempt)
    return None


# ---------------------------------------------------------------- OLX API ---

def fetch_offers():
    params = {
        "offset": 0,
        "limit": LIMIT,
        "sort_by": "created_at:desc",
    }
    if CATEGORY_ID:
        params["category_id"] = CATEGORY_ID
    if REGION_ID:
        params["region_id"] = REGION_ID
    if CITY_ID:
        params["city_id"] = CITY_ID
    if DISTRICT_ID:
        params["district_id"] = DISTRICT_ID

    log.info("OLX so'rov params: %s", params)
    data = api_get(BASE, params=params)
    if not data:
        log.error("OLX javob bermadi yoki bo'sh.")
        return []
    offers = data.get("data", []) or []
    log.info("OLX'dan olingan e'lonlar: %d", len(offers))
    return offers


def get_offer_details(item_id):
    data = api_get(f"{BASE}{item_id}/", timeout=15, tries=2)
    return (data or {}).get("data", {}) or {}


def get_phone_number(item_id):
    data = api_get(f"{BASE}{item_id}/phones/", timeout=15, tries=2)
    phones = (data or {}).get("data", {}).get("phones", []) if data else []
    if phones:
        clean = re.sub(r"[^\d+]", "", str(phones[0]))
        if clean.startswith("+"):
            return clean
        if clean.startswith("998"):
            return "+" + clean
        return "+998" + clean.lstrip("0")
    return FALLBACK_PHONE  # bo'sh bo'lsa — "Botdan ko'ring" deb yoziladi


# ------------------------------------------------------------------ PARSE ---

def get_category_id(item):
    cat = item.get("category")
    if isinstance(cat, dict) and cat.get("id"):
        return str(cat.get("id"))
    if item.get("category_id"):
        return str(item.get("category_id"))
    return ""


def get_location(item):
    loc = item.get("location") or {}
    city = (loc.get("city") or {}).get("name", "") if isinstance(loc, dict) else ""
    region = (loc.get("region") or {}).get("name", "") if isinstance(loc, dict) else ""
    district = (loc.get("district") or {}).get("name", "") if isinstance(loc, dict) else ""
    return city, region, district


def get_price(item):
    """OLX narxni params ichida yoki price maydonida qaytaradi."""
    # 1) to'g'ridan-to'g'ri price
    price = item.get("price")
    if isinstance(price, dict) and price.get("value"):
        return float(price["value"]), price.get("currency", "")

    # 2) params ro'yxati ichidan
    for p in item.get("params", []) or []:
        if p.get("key") == "price":
            val = (p.get("value") or {})
            if isinstance(val, dict) and val.get("value"):
                return float(val["value"]), val.get("currency", "")
            label = (p.get("value") or {}).get("label") if isinstance(p.get("value"), dict) else None
            if label:
                num = re.sub(r"[^\d]", "", label)
                if num:
                    return float(num), ""
    return 0.0, ""


def build_text(item, details):
    title = item.get("title", "") or ""
    desc = details.get("description", "") or item.get("description", "") or ""
    desc = re.sub(r"<[^>]+>", " ", desc)
    return f"{title}\n{desc}"


# ---------------------------------------------------------------- FILTRLASH -

def is_valid(item, details, item_id):
    text = build_text(item, details)

    # 1) Kategoriya — asosiy filtr. URL'da category_id berilgani uchun
    #    odatda hammasi to'g'ri keladi, lekin tekshirib qo'yamiz.
    cat_id = get_category_id(item)
    if CATEGORY_ID and cat_id and cat_id != str(CATEGORY_ID):
        log.info("RAD [%s]: boshqa kategoriya (%s)", item_id, cat_id)
        return False

    # 2) Manzil — Toshkent
    city, region, district = get_location(item)
    loc_full = f"{city} {region} {district}".lower()
    if loc_full.strip() and not re.search(r"toshkent|ташкент|tashkent", loc_full):
        log.info("RAD [%s]: Toshkent emas -> %s", item_id, loc_full.strip())
        return False

    # 3) Sutkalik / soatlik ijara emasligi
    hit = matches(DAILY_PATTERNS, text)
    if hit:
        log.info("RAD [%s]: sutkalik ijara belgisi -> %s", item_id, hit)
        return False

    # 4) Noturar joy (ofis, ombor, do'kon)
    hit = matches(NON_HOUSING_PATTERNS, text)
    if hit:
        log.info("RAD [%s]: noturar joy -> %s", item_id, hit)
        return False

    # 5) Sotuv e'loni (ijara so'zi umuman bo'lmasa)
    if matches(SALE_PATTERNS, text) and not matches(RENT_PATTERNS, text):
        log.info("RAD [%s]: sotuv e'loni", item_id)
        return False

    # 6) Narx oralig'i (faqat USD uchun tekshiramiz)
    value, currency = get_price(item)
    if currency.upper() in ("USD", "$") and value:
        if value < MIN_PRICE_USD or value > MAX_PRICE_USD:
            log.info("RAD [%s]: narx oraliqdan tashqari -> %s %s", item_id, value, currency)
            return False

    return True


# --------------------------------------------------------------- TELEGRAM ---

def tg_post(method, payload, timeout=20):
    try:
        res = scraper.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/{method}",
            json=payload,
            timeout=timeout,
        )
        data = res.json()
        if not data.get("ok"):
            log.error("Telegram %s xatosi: %s", method, data.get("description"))
            return None
        return data
    except Exception as e:
        log.error("Telegram %s so'rov xatosi: %s", method, e)
        return None


def send_to_telegram(caption, photo_urls, keyboard):
    if DRY_RUN:
        log.info("[DRY RUN] Yuborilardi:\n%s\nRasmlar: %d", caption, len(photo_urls))
        return True

    if not photo_urls:
        return bool(tg_post("sendMessage", {
            "chat_id": CHANNEL_ID,
            "text": caption,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
            "reply_markup": keyboard,
        }))

    if len(photo_urls) == 1:
        return bool(tg_post("sendPhoto", {
            "chat_id": CHANNEL_ID,
            "photo": photo_urls[0],
            "caption": caption[:1024],
            "parse_mode": "HTML",
            "reply_markup": keyboard,
        }))

    media = []
    for idx, url in enumerate(photo_urls[:10]):
        m = {"type": "photo", "media": url}
        if idx == 0:
            m["caption"] = caption[:1024]
            m["parse_mode"] = "HTML"
        media.append(m)

    ok = tg_post("sendMediaGroup", {"chat_id": CHANNEL_ID, "media": media}, timeout=30)
    if not ok:
        # media group ishlamasa — bitta rasm bilan urinib ko'ramiz
        return bool(tg_post("sendPhoto", {
            "chat_id": CHANNEL_ID,
            "photo": photo_urls[0],
            "caption": caption[:1024],
            "parse_mode": "HTML",
            "reply_markup": keyboard,
        }))

    # media group tugmani qo'llab-quvvatlamaydi -> alohida xabar
    tg_post("sendMessage", {
        "chat_id": CHANNEL_ID,
        "text": "🔓 Telefon raqamini ko'rish uchun:",
        "reply_markup": keyboard,
    })
    return True


# -------------------------------------------------------------- DISCOVERY ---

def discover(query):
    """Kerakli category_id / region_id / district_id ni topish uchun."""
    data = api_get(BASE, params={"query": query, "limit": 20})
    if not data:
        log.error("Discover ishlamadi.")
        return
    seen = {}
    for item in data.get("data", []) or []:
        cat = item.get("category") or {}
        loc = item.get("location") or {}
        key = (cat.get("id"), (loc.get("city") or {}).get("id"))
        if key in seen:
            continue
        seen[key] = True
        print(json.dumps({
            "category_id": cat.get("id"),
            "category": cat.get("type") or cat.get("name"),
            "region_id": (loc.get("region") or {}).get("id"),
            "region": (loc.get("region") or {}).get("name"),
            "city_id": (loc.get("city") or {}).get("id"),
            "city": (loc.get("city") or {}).get("name"),
            "district_id": (loc.get("district") or {}).get("id"),
            "district": (loc.get("district") or {}).get("name"),
            "title": item.get("title"),
        }, ensure_ascii=False))


# ------------------------------------------------------------------- MAIN ---

def main():
    log.info("--- BOT ISHGA TUSHDI (dry_run=%s) ---", DRY_RUN)

    if not DRY_RUN:
        if not validate_config() or not check_bot_access():
            return

    save_offer = None
    try:
        from database import init_db, save_offer as _save_offer
        init_db()
        save_offer = _save_offer
    except Exception as e:
        log.warning("database.py ulanmadi (%s) — DB'siz davom etamiz.", e)

    seen_ids = load_seen_ids()
    offers = fetch_offers()
    if not offers:
        return

    sent = 0
    checked = 0
    for item in offers:
        if sent >= MAX_SEND:
            break

        item_id = str(item.get("id", "") or "")
        if not item_id or item_id in seen_ids:
            continue

        checked += 1
        details = get_offer_details(item_id)
        time.sleep(0.5)  # OLX'ni charchatmaslik uchun

        if not is_valid(item, details, item_id):
            continue

        title = item.get("title", "") or "E'lon"
        value, currency = get_price(item)
        price_str = f"{int(value):,} {currency}".replace(",", " ") if value else "Kelishiladi"

        city, region, district = get_location(item)
        location_str = ", ".join([x for x in ["Toshkent", district] if x]) or "Toshkent"

        phone = get_phone_number(item_id)
        phone_line = phone if phone else "botdan ko'ring 👇"

        if save_offer:
            try:
                save_offer(item_id, title, phone or "", price_str, location_str)
            except Exception as e:
                log.warning("DB saqlash xatosi: %s", e)

        deep_link = (
            f"https://t.me/{BOT_USERNAME}?start=offer_{item_id}"
            if BOT_USERNAME else item.get("url", "https://www.olx.uz")
        )
        keyboard = {"inline_keyboard": [[
            {"text": "🔓 Telefon raqamini ko'rish", "url": deep_link}
        ]]}

        caption = (
            f"🏠 <b>{html.escape(title)}</b>\n\n"
            f"📍 Manzil: {html.escape(location_str)}\n"
            f"💵 Narx: {html.escape(price_str)}\n"
            f"📞 Tel: {html.escape(phone_line)}\n\n"
            f"📸 INSTAGRAM: {INSTAGRAM_LINK}\n"
            f"📩 TELEGRAM: {TELEGRAM_CONTACT}\n\n"
            f"#id_{item_id}"
        )

        photo_urls = []
        for p in item.get("photos", []) or []:
            link = p.get("link") or ""
            if link:
                photo_urls.append(
                    link.replace("{width}", "1000").replace("{height}", "750")
                )

        if send_to_telegram(caption, photo_urls, keyboard):
            save_seen_id(item_id)
            seen_ids.add(item_id)
            sent += 1
            log.info("✅ Yuborildi: #id_%s — %s", item_id, title[:60])
            time.sleep(2)  # Telegram flood limitidan saqlanish

    log.info("Yakunlandi. Tekshirildi: %d, yuborildi: %d", checked, sent)


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "discover":
        discover(" ".join(args[1:]) or "kvartira ijaraga Toshkent")
    else:
        if args and args[0] in ("test", "dry", "dry-run"):
            DRY_RUN = True
        main()
