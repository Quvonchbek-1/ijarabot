import os
import re
import html
import time
import logging
import subprocess
import sys

try:
    import cloudscraper
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "cloudscraper"])
    import cloudscraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("olx_bot")

BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
CHANNEL_ID = os.environ.get("CHANNEL_ID", "").strip()
BOT_USERNAME = os.environ.get("BOT_USERNAME", "").strip()

API_URL = "https://www.olx.uz/api/v1/offers/?offset=0&limit=50"
SEEN_FILE = "seen_ids.txt"
INSTAGRAM_LINK = "toshkent_ijaraga"
TELEGRAM_CONTACT = "@turayev_bek"

scraper = cloudscraper.create_scraper(
    browser={
        'browser': 'chrome',
        'platform': 'windows',
        'desktop': True
    }
)


def validate_config():
    problems = []
    if not BOT_TOKEN:
        problems.append("BOT_TOKEN bo'sh.")
    if not CHANNEL_ID:
        problems.append("CHANNEL_ID bo'sh.")
    if problems:
        for p in problems:
            log.error(p)
        return False
    return True


def check_bot_access():
    try:
        res = scraper.get(
            f"https://api.telegram.org/bot{BOT_TOKEN}/getChat",
            params={"chat_id": CHANNEL_ID},
            timeout=10,
        )
        data = res.json()
        if not data.get("ok"):
            log.error("getChat xatosi: %s", data.get("description"))
            return False
        log.info("Bot chatni ko'ra oladi: %s", data.get("result", {}).get("title", CHANNEL_ID))
        return True
    except Exception as e:
        log.error("Bot huquqlarini tekshirishda xato: %s", e)
        return False


def load_seen_ids():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            return set(line.strip() for line in f if line.strip())
    return set()


def save_seen_id(item_id):
    with open(SEEN_FILE, "a", encoding="utf-8") as f:
        f.write(f"{item_id}\n")


def get_phone_number(item_id):
    try:
        phone_url = f"https://www.olx.uz/api/v1/offers/{item_id}/phones/"
        res = scraper.get(phone_url, timeout=10)
        if res.status_code == 200:
            phones = res.json().get("data", {}).get("phones", [])
            if phones:
                clean = re.sub(r"[^\d+]", "", phones[0])
                if not clean.startswith("+") and clean.startswith("998"):
                    clean = "+" + clean
                elif not clean.startswith("+"):
                    clean = "+998" + clean
                return clean
    except Exception as e:
        log.warning("Tel olishda xatolik (%s): %s", item_id, e)
    return "+998952522225"


def get_offer_details(item_id):
    try:
        url = f"https://www.olx.uz/api/v1/offers/{item_id}/"
        res = scraper.get(url, timeout=10)
        if res.status_code == 200:
            return res.json().get("data", {})
    except Exception as e:
        log.warning("Tafsilot olish xatolik (%s): %s", item_id, e)
    return {}


def is_valid_housing_rental(item, details):
    title = item.get("title", "")
    description = details.get("description", "")
    full_text = f"{title} {description}".lower()

    # 1. Manzil: Faqat Toshkent shahri
    location_data = item.get("location", {})
    city_name = location_data.get("city", {}).get("name", "") if isinstance(location_data, dict) else ""
    region_name = location_data.get("region", {}).get("name", "") if isinstance(location_data, dict) else ""
    loc_full = f"{city_name} {region_name}".lower()

    if "toshkent" not in loc_full and "ташкент" not in loc_full:
        return False

    # 2. Narx filtri ($300 - $2000, agar narx yo'q yoki mos kelmasa - tashlab yuboramiz)
    price_obj = item.get("price", {})
    price_val = price_obj.get("value", 0) if isinstance(price_obj, dict) else 0
    price_curr = price_obj.get("currency", "USD") if isinstance(price_obj, dict) else "USD"

    if not price_val or price_val <= 0:
        return False

    price_in_usd = price_val
    if price_curr.upper() in ["UZS", "SUM", "СУМ"]:
        price_in_usd = price_val / 12800.0  # O'rtacha kurs bo'yicha dollarga o'tkazamiz

    if not (300 <= price_in_usd <= 2000):
        return False

    # 3. Haqiqiy ko'chmas mulk parametri tekshiruvi (Texnikalarda 'rooms' parametri bo'lmaydi)
    params = details.get("params", [])
    has_rooms_param = any(p.get("key") == "rooms" for p in params)
    if not has_rooms_param:
        return False

    # 4. Qora ro'yxat (Texnika, sutkalik va boshqa narsalar)
    forbidden_words = [
        "ziffler", "qozon", "kotyol", "katyol", "kolonka", "konditsioner", "televizor",
        "sovutgich", "kir yuvish", "pechka", "plita", "aspirator", "duxovka", "agregat",
        "generator", "stabilizator", "nasos", "radiator", "artel", "lg", "samsung", "bosch",
        "sutka", "сутки", "sutkaga", "kunlik", "soatiga", "soatlik", "час", "посуточно",
        "avto", "mashina", "zapchast", "telefon", "iphone", "noutbuk", "kompyuter",
        "vakansiya", "vacancy", "xizmat", "kurs", "reklama", "ishga", "gilam", "matras"
    ]
    if any(word in full_text for word in forbidden_words):
        return False

    # 5. Sotishga oid so'zlar (ijarasiz)
    sale_words = ["sotiladi", "продается", "sotish", "выкуп", "ipoteka", "kreditga"]
    rental_words = ["ijara", "аренда", "arenda", "сдается", "сдам", "beriladi"]
    
    has_sale = any(w in full_text for w in sale_words)
    has_rental = any(w in full_text for w in rental_words)

    if has_sale and not has_rental:
        return False

    return True


def send_to_telegram(caption, photo_urls, keyboard, retries=2):
    for attempt in range(1, retries + 1):
        try:
            if not photo_urls:
                res = scraper.post(
                    f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                    json={
                        "chat_id": CHANNEL_ID,
                        "text": caption,
                        "parse_mode": "HTML",
                        "reply_markup": keyboard,
                    },
                    timeout=15,
                )
            elif len(photo_urls) == 1:
                res = scraper.post(
                    f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto",
                    json={
                        "chat_id": CHANNEL_ID,
                        "photo": photo_urls[0],
                        "caption": caption,
                        "parse_mode": "HTML",
                        "reply_markup": keyboard,
                    },
                    timeout=15,
                )
            else:
                media_list = []
                for idx, url in enumerate(photo_urls[:10]):
                    media_item = {
                        "type": "photo",
                        "media": url
                    }
                    if idx == 0:
                        media_item["caption"] = caption
                        media_item["parse_mode"] = "HTML"
                    media_list.append(media_item)

                res = scraper.post(
                    f"https://api.telegram.org/bot{BOT_TOKEN}/sendMediaGroup",
                    json={
                        "chat_id": CHANNEL_ID,
                        "media": media_list
                    },
                    timeout=20,
                )

                if res.status_code == 200:
                    scraper.post(
                        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                        json={
                            "chat_id": CHANNEL_ID,
                            "text": "🔓 Telefon raqamini ko'rish uchun:",
                            "reply_markup": keyboard
                        },
                        timeout=10,
                    )

            if res.status_code == 200:
                return True

            data = res.json()
            log.error("Telegram xatosi: %s — %s", res.status_code, data.get("description"))
            return False
        except Exception as e:
            log.error("Telegramga yuborishda xato: %s", e)
            time.sleep(2)
    return False


def main():
    log.info("--- BOT ISHGA TUSHDI ---")
    if not validate_config() or not check_bot_access():
        return

    from database import init_db, save_offer
    init_db()
    seen_ids = load_seen_ids()

    try:
        log.info("OLX API'dan e'lonlar olinmoqda...")
        res = scraper.get(API_URL, timeout=20)
        log.info("OLX API javob kodi: %s", res.status_code)
        
        if res.status_code != 200:
            log.error("OLX javob bermadi! Status code: %s", res.status_code)
            return

        offers = res.json().get("data", [])
        log.info("OLX'dan olingan umumiy e'lonlar soni: %d", len(offers))
    except Exception as x:
        log.error("OLX so'rov xatosi: %s", x)
        return

    sent_count = 0
    for item in offers:
        item_id = str(item.get("id", ""))
        title = item.get("title", "")

        if not item_id or item_id in seen_ids:
            continue

        details = get_offer_details(item_id)
        
        # Keskin va kuchaytirilgan filtr
        if not is_valid_housing_rental(item, details):
            continue

        price_obj = item.get("price", {})
        price_val = price_obj.get("value", 0) if isinstance(price_obj, dict) else 0
        price_curr = price_obj.get("currency", "USD") if isinstance(price_obj, dict) else "USD"
        price_str = f"{price_val} {price_curr}" if price_val else "Kelishilgan holda"

        location_data = item.get("location", {})
        district_name = location_data.get("district", {}).get("name", "Toshkent") if isinstance(location_data, dict) else "Toshkent"
        location_str = f"Toshkent, {district_name}"

        phone = get_phone_number(item_id)

        save_offer(item_id, title, phone, price_str, location_str)

        deep_link = f"https://t.me/{BOT_USERNAME}?start=offer_{item_id}" if BOT_USERNAME else "https://t.me"
        keyboard = {
            "inline_keyboard": [[
                {"text": "🔓 Telefon raqamini ko'rish", "url": deep_link}
            ]]
        }

        safe_title = html.escape(title)
        safe_location = html.escape(location_str)
        safe_price = html.escape(price_str)

        # Eski formatga o'xshash toza shablon
        caption = (
            f"🏠 <b>{safe_title}</b>\n\n"
            f"📍 Manzil: {safe_location}\n"
            f"💵 Narx: {safe_price}\n"
            f"📞 Tel: {phone}\n\n"
            f"📸 INSTAGRAM: {INSTAGRAM_LINK}\n"
            f"📩 TELEGRAM: {TELEGRAM_CONTACT}\n\n"
            f"#id_{item_id}"
        )

        photos = item.get("photos", [])
        photo_urls = [
            p.get("link", "").replace("{width}", "1000").replace("{height}", "750")
            for p in photos if p.get("link")
        ]

        ok = send_to_telegram(caption, photo_urls, keyboard)

        if ok:
            save_seen_id(item_id)
            seen_ids.add(item_id)
            log.info("✅ Toza uy e'loni kanalga joylandi: #id_%s", item_id)
            sent_count += 1
            if sent_count >= 2:
                break

    log.info("Yakunlandi. Jami yuborilgan: %d", sent_count)


if __name__ == "__main__":
    main()
