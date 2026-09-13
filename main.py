import os
import re
import sys
import requests
from curl_cffi import requests as cffi_requests

# Baza bilan ishlash funksiyalarini xavfsiz yuklash
try:
    from database import init_db, save_offer
except ImportError:
    def init_db(): pass
    def save_offer(a, b, c, d, e): pass

BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
CHANNEL_ID = os.environ.get("CHANNEL_ID", "").strip()
BOT_USERNAME = os.environ.get("BOT_USERNAME", "").strip()

API_URL = "https://www.olx.uz/api/v1/offers/?offset=0&limit=50"
SEEN_FILE = "seen_ids.txt"
COUNTER_FILE = "counter.txt"
INSTAGRAM_LINK = "https://www.instagram.com/toshkent_ijaraga?utm_source=qr&stkn=bGdocHlnNWMwYmJz"

def get_usd_rate():
    """Markaziy Bank API'dan dollar kursini olish"""
    try:
        res = requests.get("https://cbu.uz/uz/arkhiv-kursov-valyut/json/USD/", timeout=10)
        if res.status_code == 200:
            rate = float(res.json()[0]["Rate"])
            print(f"💰 Joriy dollar kursi: 1 USD = {rate} UZS")
            return rate
    except Exception as e:
        print(f"⚠️ Valyuta kursini olishda xatolik (standart 12800 UZS ishlatiladi): {e}")
    return 12800.0

USD_RATE = get_usd_rate()

def load_seen_ids():
    if os.path.exists(SEEN_FILE):
        try:
            with open(SEEN_FILE, "r", encoding="utf-8") as f:
                return set(line.strip() for line in f if line.strip())
        except Exception:
            pass
    return set()

def save_seen_id(item_id):
    try:
        with open(SEEN_FILE, "a", encoding="utf-8") as f:
            f.write(f"{item_id}\n")
    except Exception as e:
        print(f"Xato (seen_ids saqlash): {e}")

def get_next_counter():
    if os.path.exists(COUNTER_FILE):
        try:
            with open(COUNTER_FILE, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    return int(content)
        except Exception:
            pass
    return 1

def save_counter(count):
    try:
        with open(COUNTER_FILE, "w", encoding="utf-8") as f:
            f.write(str(count))
    except Exception as e:
        print(f"Xato (counter saqlash): {e}")

def get_phone_number(item_id):
    try:
        phone_url = f"https://www.olx.uz/api/v1/offers/{item_id}/phones/"
        res = cffi_requests.get(phone_url, impersonate="chrome120", timeout=10)
        if res.status_code == 200:
            phones = res.json().get("data", {}).get("phones", [])
            if phones:
                clean_phone = re.sub(r'[^\d+]', '', phones[0])
                if not clean_phone.startswith('+') and clean_phone.startswith('998'):
                    clean_phone = '+' + clean_phone
                elif not clean_phone.startswith('+'):
                    clean_phone = '+998' + clean_phone
                return clean_phone
    except Exception as e:
        print(f"Tel raqam olishda xato (ID: {item_id}): {e}")
    return "Ko'rsatilmagan"

def extract_price_in_usd(item):
    price_obj = item.get("price", {})
    if isinstance(price_obj, dict):
        val = price_obj.get("value")
        curr = price_obj.get("currency")
        if val is not None and val > 0:
            if curr == "UZS":
                return round(val / USD_RATE)
            else:
                return int(val)
    return None

def send_telegram_teaser(caption, photos, item_id):
    if not BOT_TOKEN or not CHANNEL_ID:
        print("❌ XATOLIK: BOT_TOKEN yoki CHANNEL_ID GitHub Secrets'da topilmadi!")
        return False

    valid_photos = []
    if isinstance(photos, list):
        for p in photos[:10]:
            if isinstance(p, dict) and p.get("link"):
                valid_photos.append(p.get("link").replace("{width}", "1000").replace("{height}", "750"))

    bot_deep_link = f"https://t.me/{BOT_USERNAME}?start=offer_{item_id}" if BOT_USERNAME else "https://t.me"
    reply_markup = {
        "inline_keyboard": [[
            {"text": "🔓 Telefon raqamini ko'rish", "url": bot_deep_link}
        ]]
    }

    try:
        if len(valid_photos) >= 2:
            media = [{"type": "photo", "media": url} for url in valid_photos]
            media[0]["caption"] = caption
            media[0]["parse_mode"] = "HTML"
            
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMediaGroup", json={"chat_id": CHANNEL_ID, "media": media}, timeout=15)
            r = requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", json={
                "chat_id": CHANNEL_ID,
                "text": "👇 E'lon egasi bilan bog'lanish uchun tugmani bosing:",
                "reply_markup": reply_markup
            }, timeout=15)
            return r.status_code == 200
        elif len(valid_photos) == 1:
            r = requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto", json={
                "chat_id": CHANNEL_ID,
                "photo": valid_photos[0],
                "caption": caption,
                "parse_mode": "HTML",
                "reply_markup": reply_markup
            }, timeout=15)
            return r.status_code == 200
        else:
            r = requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", json={
                "chat_id": CHANNEL_ID,
                "text": caption,
                "parse_mode": "HTML",
                "reply_markup": reply_markup
            }, timeout=15)
            return r.status_code == 200
    except Exception as e:
        print(f"Telegram API yuborishda xatolik: {e}")
        return False

def main():
    print("🚀 SCRAPER ISHGA TUSHDI")
    
    try:
        init_db()
    except Exception as e:
        print(f"Baza yuklanishida ogohlantirish: {e}")

    seen_ids = load_seen_ids()
    post_number = get_next_counter()

    print(f"📊 Ilgari ko'rilgan e'lonlar soni: {len(seen_ids)}")
    print("🌐 OLX API'ga so'rov yuborilmoqda...")

    try:
        res = cffi_requests.get(API_URL, impersonate="chrome120", timeout=20)
        if res.status_code != 200:
            print(f"❌ OLX serveri xato javob berdi: HTTP {res.status_code}")
            return

        data = res.json()
        offers = data.get("data", [])
        print(f"📦 OLX'dan kelgan jami e'lonlar: {len(offers)} ta")
    except Exception as e:
        print(f"❌ OLX so'rovida xatolik: {e}")
        return

    sent_count = 0
    for item in offers:
        item_id = str(item.get("id", ""))
        if not item_id or item_id in seen_ids:
            continue

        title = item.get("title", "")
        title_lower = title.lower()

        # 1. Shahar filtri (Toshkent / Ташкент)
        city_name = ""
        location_data = item.get("location", {})
        if isinstance(location_data, dict):
            city_obj = location_data.get("city", {})
            if isinstance(city_obj, dict):
                city_name = city_obj.get("name", "")

        if "toshkent" not in city_name.lower() and "ташкент" not in city_name.lower():
            continue

        # 2. Kunlik/Sutkalik ijara e'lonlarini tashlab yuborish
        if any(w in title_lower for w in ["sutka", "сутки", "sutkaga", "kunlik", "посуточно"]):
            continue

        # 3. Narx filtri ($350 - $1300 USD)
        usd_price = extract_price_in_usd(item)
        if not usd_price or not (350 <= usd_price <= 1300):
            continue

        # Tuman va manzil
        district_name = ""
        if isinstance(location_data, dict):
            dist_obj = location_data.get("district", {})
            if isinstance(dist_obj, dict):
                district_name = dist_obj.get("name", "")

        location_str = f"{city_name}, {district_name}".strip(", ")
        phone_number = get_phone_number(item_id)

        try:
            save_offer(item_id, title, phone_number, usd_price, location_str)
        except Exception as e:
            print(f"Baza saqlash: {e}")

        masked_phone = "+998 90 *** ** **"
        caption = (
            f"🏠 <b>{title}</b>\n"
            f"📍 <b>Manzil:</b> {location_str}\n\n"
            f"💵 <b>Narx:</b> {usd_price}$\n"
            f"📞 <b>Tel:</b> {masked_phone}\n\n"
            f"📸 <b>INSTAGRAM:</b> <a href='{INSTAGRAM_LINK}'>toshkent_ijaraga</a>\n\n"
            f"#id_{post_number}"
        )

        success = send_telegram_teaser(caption, item.get("photos", []), item_id)
        if success:
            print(f"✅ KANALGA YUBORILDI: #{post_number} - {title[:35]}... ({usd_price}$)")
            save_seen_id(item_id)
            post_number += 1
            save_counter(post_number)
            sent_count += 1
        else:
            print(f"⚠️ Telegramga yuborib bo'lmadi (ID: {item_id})")

        if sent_count >= 5:
            break

    print(f"🏁 JARAYON YAKUNLANDI: Jami {sent_count} ta yangi e'lon kanalga joylandi.")

if __name__ == "__main__":
    main()
