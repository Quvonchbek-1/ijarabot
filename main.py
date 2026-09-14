import os
import re
import requests

BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
CHANNEL_ID = os.environ.get("CHANNEL_ID", "").strip()
BOT_USERNAME = os.environ.get("BOT_USERNAME", "").strip()

API_URL = "https://www.olx.uz/api/v1/offers/?offset=0&limit=20"
SEEN_FILE = "seen_ids.txt"
INSTAGRAM_LINK = "https://www.instagram.com/toshkent_ijaraga"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "uz,ru;q=0.9,en;q=0.8"
}

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
        res = requests.get(phone_url, headers=HEADERS, timeout=10)
        if res.status_code == 200:
            phones = res.json().get("data", {}).get("phones", [])
            if phones:
                clean = re.sub(r'[^\d+]', '', phones[0])
                if not clean.startswith('+') and clean.startswith('998'):
                    clean = '+' + clean
                elif not clean.startswith('+'):
                    clean = '+998' + clean
                return clean
    except Exception as e:
        print(f"Tel olishda xatolik ({item_id}): {e}")
    return "Ko'rsatilmagan"

def get_offer_details(item_id):
    try:
        url = f"https://www.olx.uz/api/v1/offers/{item_id}/"
        res = requests.get(url, headers=HEADERS, timeout=10)
        if res.status_code == 200:
            return res.json().get("data", {})
    except Exception as e:
        print(f"Tafsilot olish xatolik ({item_id}): {e}")
    return {}

def main():
    print(f"--- BOT ISHGA TUSHDI ---")
    print(f"CHANNEL_ID: {CHANNEL_ID}")
    print(f"BOT_TOKEN mavjudligi: {'HA' if BOT_TOKEN else 'YOQ'}")

    from database import init_db, save_offer
    init_db()
    seen_ids = load_seen_ids()
    print(f"Oldindan ko'rilgan e'lonlar soni: {len(seen_ids)}")

    try:
        res = requests.get(API_URL, headers=HEADERS, timeout=20)
        print(f"OLX API javob kodi: {res.status_code}")
        if res.status_code != 200:
            print(f"OLX API xatosi!")
            return
        offers = res.json().get("data", [])
        print(f"OLX'dan olingan e'lonlar soni: {len(offers)}")
    except Exception as e:
        print(f"OLX so'rov xatosi: {e}")
        return

    sent_count = 0
    for item in offers:
        item_id = str(item.get("id", ""))
        title = item.get("title", "")
        
        if not item_id:
            continue
            
        if item_id in seen_ids:
            print(f"O'tkazib yuborildi (oldindan bor): {title[:20]} (ID: {item_id})")
            continue

        title_lower = title.lower()
        location_data = item.get("location", {})
        city_name = location_data.get("city", {}).get("name", "") if isinstance(location_data, dict) else ""
        
        print(f"Tekshirilmoqda: {title} | Shahar: {city_name}")

        if "toshkent" not in city_name.lower() and "ташкент" not in city_name.lower():
            print(f"-> Toshkent emas, tashlab yuborildi.")
            continue

        if any(w in title_lower for w in ["sutka", "сутки", "sutkaga", "kunlik"]):
            print(f"-> Sutkalik e'lon, tashlab yuborildi.")
            continue

        details = get_offer_details(item_id)
        description = details.get("description", "")
        
        description_clean = re.sub(r'<br\s*/?>', '\n', description)
        description_clean = re.sub(r'<[^>]+>', '', description_clean).strip()
        if len(description_clean) > 400:
            description_clean = description_clean[:397] + "..."

        price_obj = item.get("price", {})
        price_val = price_obj.get("value", 0) if isinstance(price_obj, dict) else 0
        price_curr = price_obj.get("currency", "USD") if isinstance(price_obj, dict) else "USD"
        price_str = f"{price_val} {price_curr}" if price_val else "Kelishilgan holda"

        district_name = location_data.get("district", {}).get("name", "") if isinstance(location_data, dict) else ""
        location_str = f"{city_name}, {district_name}".strip(", ")

        phone = get_phone_number(item_id)
        save_offer(item_id, title, phone, price_str, location_str)

        deep_link = f"https://t.me/{BOT_USERNAME}?start=offer_{item_id}" if BOT_USERNAME else "https://t.me"
        keyboard = {
            "inline_keyboard": [[
                {"text": "🔓 Telefon raqamini ko'rish", "url": deep_link}
            ]]
        }

        caption = (
            f"🏠 <b>{title}</b>\n"
            f"📍 <b>Manzil:</b> {location_str}\n"
            f"💵 <b>Narx:</b> {price_str}\n\n"
            f"📝 <b>Tavsif:</b>\n{description_clean}\n\n"
            f"📞 <b>Tel:</b> +998 90 *** ** **\n\n"
            f"📸 <b>INSTAGRAM:</b> <a href='{INSTAGRAM_LINK}'>toshkent_ijaraga</a>"
        )

        photos = item.get("photos", [])
        valid_photo = photos[0].get("link", "").replace("{width}", "1000").replace("{height}", "750") if photos else None

        try:
            if valid_photo:
                tg_res = requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto", json={
                    "chat_id": CHANNEL_ID, "photo": valid_photo, "caption": caption, "parse_mode": "HTML", "reply_markup": keyboard
                }, timeout=15)
            else:
                tg_res = requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", json={
                    "chat_id": CHANNEL_ID, "text": caption, "parse_mode": "HTML", "reply_markup": keyboard
                }, timeout=15)

            print(f"Telegram API javobi: {tg_res.status_code} - {tg_res.text}")

            if tg_res.status_code == 200:
                save_seen_id(item_id)
                seen_ids.add(item_id)
                print(f"✅ Kanalga muvaffaqiyatli joylandi: {title[:30]}")
                sent_count += 1
                if sent_count >= 2:
                    break
            else:
                print(f"❌ Telegramga yuborishda xatolik yuz berdi!")
        except Exception as e:
            print(f"Telegramga so'rov yuborishda xato: {e}")

if __name__ == "__main__":
    main()
