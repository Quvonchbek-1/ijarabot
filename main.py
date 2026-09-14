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

# Umumiy so'nggi e'lonlar (0 ta chiqib qolishining oldini oladi, filtrlar pastda bajariladi)
API_URL = "https://www.olx.uz/api/v1/offers/?offset=0&limit=50"
SEEN_FILE = "seen_ids.txt"
INSTAGRAM_LINK = "https://www.instagram.com/toshkent_ijaraga"

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
    return "Ko'rsatilmagan"


def get_offer_details(item_id):
    try:
        url = f"https://www.olx.uz/api/v1/offers/{item_id}/"
        res = scraper.get(url, timeout=10)
        if res.status_code == 200:
            return res.json().get("data", {})
    except Exception as e:
        log.warning("Tafsilot olish xatolik (%s): %s", item_id, e)
    return {}


def send_to_telegram(caption, photo_url, keyboard, retries=2):
    for attempt in range(1, retries + 1):
        try:
            if photo_url:
                res = scraper.post(
                    f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto",
                    json={
                        "chat_id": CHANNEL_ID,
                        "photo": photo_url,
                        "caption": caption,
                        "parse_mode": "HTML",
                        "reply_markup": keyboard,
                    },
                    timeout=15,
                )
            else:
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

            if res.status_code == 200:
                return True

            data = res.json()
            log.error("Telegram xatosi: %s — %s", res.status_code, data.get("description"))
            if photo_url and "photo" in str(data.get("description", "")).lower():
                photo_url = None
                continue
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
    except Exception as e:
        log.error("OLX so'rov xatosi: %s", e)
        return

    sent_count = 0
    for item in offers:
        item_id = str(item.get("id", ""))
        title = item.get("title", "")

        if not item_id or item_id in seen_ids:
            continue

        details = get_offer_details(item_id)
        description = details.get("description", "")
        
        title_lower = title.lower()
        desc_lower = description.lower()
        full_text = f"{title_lower} {desc_lower}"

        # 1. Hududni tekshirish (Faqat Toshkent shahri)
        location_data = item.get("location", {})
        city_name = location_data.get("city", {}).get("name", "") if isinstance(location_data, dict) else ""
        region_name = location_data.get("region", {}).get("name", "") if isinstance(location_data, dict) else ""
        loc_full = f"{city_name} {region_name}".lower()

        if "toshkent" not in loc_full and "ташкент" not in loc_full:
            continue

        # 2. Faqat uy/kvartira ijarasiga oidligini tekshiramiz (boshqa narsalarni o'tkazib yubormaslik uchun)
        housing_keywords = ["kvartira", "kv", "dom", "uy", "komnata", "квартира", "дом", "комната", "arrenda", "ijara", "аренда"]
        if not any(kw in full_text for kw in housing_keywords):
            continue

        # 3. Sutkalik / kunlik e'lonlarni filtrlab tashlaymiz
        daily_keywords = ["sutka", "сутки", "sutkaga", "kunlik", "soatiga", "soatlik", "час", "посуточно"]
        if any(w in full_text for w in daily_keywords):
            continue

        # 4. Sotuvdagilarni chiqarib tashlab, faqat ijaraga qaratamiz
        if any(w in full_text for w in ["sotiladi", "продается", "sotish"]) and not any(w in full_text for w in ["ijara", "аренда", "arenda"]):
            continue

        description_clean = re.sub(r"<br\s*/?>", "\n", description)
        description_clean = re.sub(r"<[^>]+>", "", description_clean).strip()
        if len(description_clean) > 350:
            description_clean = description_clean[:347] + "..."

        price_obj = item.get("price", {})
        price_val = price_obj.get("value", 0) if isinstance(price_obj, dict) else 0
        price_curr = price_obj.get("currency", "USD") if isinstance(price_obj, dict) else "USD"
        price_str = f"{price_val} {price_curr}" if price_val else "Kelishilgan holda"

        district_name = location_data.get("district", {}).get("name", "") if isinstance(location_data, dict) else ""
        location_str = f"Toshkent, {district_name}".strip(", ")

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
        safe_description = html.escape(description_clean)

        # Chiroyli, stiker va zamonaviy bezatilgan shablon
        caption = (
            f"🏢 <b>YANGI UY IJARA E'LONI!</b> 🔑\n\n"
            f"📌 <b>Sarlavha:</b> {safe_title}\n\n"
            f"💰 <b>Narxi:</b> <code>{safe_price}</code> 💵\n"
            f"📍 <b>Manzil:</b> {safe_location} 🌆\n\n"
            f"📝 <b>Tavsif:</b>\n"
            f"<i>{safe_description}</i>\n\n"
            f"📞 <b>Aloqa:</b> +998 (90) *** ** **\n"
            f"✨ <i>Egasining raqamini ko'rish uchun pastdagi tugmani bosing!</i> 👇\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"📢 <b>Bizning kanal:</b> <a href='{INSTAGRAM_LINK}'>toshkent_ijaraga</a> 🚀"
        )

        photos = item.get("photos", [])
        valid_photo = (
            photos[0].get("link", "").replace("{width}", "1000").replace("{height}", "750")
            if photos else None
        )

        ok = send_to_telegram(caption, valid_photo, keyboard)

        if ok:
            save_seen_id(item_id)
            seen_ids.add(item_id)
            log.info("✅ Chiroyli uy e'loni kanalga joylandi: %s", title[:30])
            sent_count += 1
            if sent_count >= 2:
                break

    log.info("Yakunlandi. Jami yuborilgan: %d", sent_count)


if __name__ == "__main__":
    main()
