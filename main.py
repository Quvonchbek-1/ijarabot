import os
import re
import requests
from curl_cffi import requests as cffi_requests
from database import init_db, save_offer

BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
CHANNEL_ID = os.environ.get("CHANNEL_ID", "").strip()
BOT_USERNAME = os.environ.get("BOT_USERNAME", "").strip()

API_URL = "https://www.olx.uz/api/v1/offers/?offset=0&limit=50&query=ijara+kvartira"
SEEN_FILE = "seen_ids.txt"
COUNTER_FILE = "counter.txt"
INSTAGRAM_LINK = "https://www.instagram.com/toshkent_ijaraga?utm_source=qr&stkn=bGdocHlnNWMwYmJz"

def get_usd_rate():
    try:
        res = requests.get("https://cbu.uz/uz/arkhiv-kursov-valyut/json/USD/", timeout=5)
        if res.status_code == 200:
            return float(res.json()[0]["Rate"])
    except Exception as e:
        print(f"Valyuta kursini olishda xato: {e}")
    return 12800.0

USD_RATE = get_usd_rate()

def load_seen_ids():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            return set(line.strip() for line in f if line.strip())
    return set()

def save_seen_id(item_id):
    with open(SEEN_FILE, "a", encoding="utf-8") as f:
        f.write(f"{item_id}\n")

def get_next_counter():
    if os.path.exists(COUNTER_FILE):
        with open(COUNTER_FILE, "r", encoding="utf-8") as f:
            try:
                content = f.read().strip()
                if content: return int(content)
            except: pass
    return 1

def save_counter(count):
    with open(COUNTER_FILE, "w", encoding="utf-8") as f:
        f.write(str(count))

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
        val, curr = price_obj.get("value"), price_obj.get("currency")
        if val:
            return round(val / USD_RATE) if curr == "UZS" else int(val)
    return None

def send_telegram_teaser(caption, photos, item_id):
    valid_photos = [p.get("link", "").replace("{width}", "1000").replace("{height}", "750") for p in photos[:10] if p.get("link")]
    bot_deep_link = f"https://t.me/{BOT_USERNAME}?start=offer_{item_id}"
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
            
            res1 = requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMediaGroup", json={"chat_id": CHANNEL_ID, "media": media}, timeout=15)
            res2 = requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", json={
                "chat_id": CHANNEL_ID,
                "text": "👇 E'lon egasi bilan bog'lanish uchun tugmani bosing:",
                "reply_markup": reply_markup
            }, timeout=15)
            print(f"Telegram javobi: {res2.status_code}")
        elif len(valid_photos) == 1:
            res = requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto", json={
                "chat_id": CHANNEL_ID,
                "photo": valid_photos[0],
                "caption": caption,
                "parse_mode": "HTML",
                "reply_markup": reply_markup
            }, timeout=15)
            print(f"Telegram javobi: {res.status_code}")
    except Exception as e:
        print(f"Telegramga yuborishda xato: {e}")

def main():
    init_db()
    seen_ids = load_seen_ids()
    post_number = get_next_counter()

    print("OLX'dan e'lonlar olinmoqda...")
    try:
        res = cffi_requests.get(API_URL, impersonate="chrome120", timeout=15)
        offers = res.json().get("data", [])
        print(f"OLX'dan {len(offers)} ta e'lon keldi.")
    except Exception as e:
        print(f"OLX API so'rovida xatolik: {e}")
        return

    sent_count = 0
    for item in offers:
        item_id = str(item.get("id"))
        if item_id in seen_ids:
            continue

        city_name = item.get("location", {}).get("city", {}).get("name", "")
        if "toshkent" not in city_name.lower() and "ташкент" not in city_name.lower():
            continue

        usd_price = extract_price_in_usd(item)
        if not usd_price or not (350 <= usd_price <= 1300):
            print(f"E'lon narxi mos kelmadi: {usd_price}$ (ID: {item_id})")
            continue

        title = item.get("title", "Yangi e'lon")
        district_name = item.get("location", {}).get("district", {}).get("name", "")
        location_str = f"{city_name}, {district_name}".strip(", ")
        phone_number = get_phone_number(item_id)

        save_offer(item_id, title, phone_number, usd_price, location_str)

        masked_phone = "+998 90 *** ** **"
        caption = (
            f"🏠 <b>{title}</b>\n"
            f"📍 <b>Manzil:</b> {location_str}\n\n"
            f"💵 <b>Narx:</b> {usd_price}$\n"
            f"📞 <b>Tel:</b> {masked_phone}\n\n"
            f"📸 <b>INSTAGRAM:</b> <a href='{INSTAGRAM_LINK}'>toshkent_ijaraga</a>\n\n"
            f"#id_{post_number}"
        )

        send_telegram_teaser(caption, item.get("photos", []), item_id)
        save_seen_id(item_id)
        post_number += 1
        save_counter(post_number)
        sent_count += 1
        print(f"Yangi e'lon yuborildi: #{post_number} (ID: {item_id})")

        if sent_count >= 5:
            break

    if sent_count == 0:
        print("Yangi va mezonlarga mos e'lon topilmadi.")

if __name__ == "__main__":
    main()
