import os
import re
import requests
from curl_cffi import requests as cffi_requests

BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
CHANNEL_ID = os.environ.get("CHANNEL_ID", "").strip()

# API so'rovi toza va barqaror formatda (OLX dagi barcha kvartira ijaralarini oladi)
API_URL = "https://www.olx.uz/api/v1/offers/?offset=0&limit=50&query=ijara+kvartira"
SEEN_FILE = "seen_ids.txt"
COUNTER_FILE = "counter.txt"

INSTAGRAM_LINK = "https://www.instagram.com/toshkent_ijaraga?utm_source=qr&stkn=bGdocHlnNWMwYmJz"

def get_usd_rate():
    """Markaziy Bankdan jonli dollar kursini olish"""
    try:
        res = requests.get("https://cbu.uz/uz/arkhiv-kursov-valyut/json/USD/", timeout=5)
        if res.status_code == 200:
            data = res.json()
            if data and "Rate" in data[0]:
                rate = float(data[0]["Rate"])
                print(f"MB Real USD kursi: {rate} UZS")
                return rate
    except Exception as e:
        print(f"Kurs olishda xato, standart ishlatiladi: {e}")
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
                if content:
                    return int(content)
            except ValueError:
                pass
    return 1

def save_counter(count):
    with open(COUNTER_FILE, "w", encoding="utf-8") as f:
        f.write(str(count))

def get_phone_number(item_id):
    try:
        phone_url = f"https://www.olx.uz/api/v1/offers/{item_id}/phones/"
        res = cffi_requests.get(
            phone_url,
            impersonate="chrome120",
            headers={
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "uz-UZ,uz;q=0.9,ru;q=0.8",
                "Referer": "https://www.olx.uz/"
            },
            timeout=10
        )
        if res.status_code == 200:
            data = res.json()
            phones = data.get("data", {}).get("phones", [])
            if phones:
                phone = phones[0]
                clean_phone = re.sub(r'[^\d+]', '', phone)
                if not clean_phone.startswith('+') and clean_phone.startswith('998'):
                    clean_phone = '+' + clean_phone
                elif not clean_phone.startswith('+'):
                    clean_phone = '+998' + clean_phone
                
                return f'<a href="tel:{clean_phone}">{clean_phone}</a>'
    except Exception as e:
        print(f"Raqam olishda xatolik #{item_id}: {e}")
    return "Ko'rsatilmagan"

def parse_target_audience(text):
    text_lower = text.lower()
    targets = []

    if any(w in text_lower for w in ["oila", "oilaga", "семь"]):
        targets.append("• Oilaga")
    if any(w in text_lower for w in ["qiz", "qizlar", "qizlarga", "девуш"]):
        targets.append("• Talaba / ishchi qizlarga")
    if any(w in text_lower for w in ["yigit", "yigitlar", "yigitlarga", "парне"]):
        targets.append("• Ishchi / talaba yigitlarga")

    if targets:
        return "\n".join(targets)
    return "• Hammaga"

def extract_price_in_usd(item):
    """E'lon narxini tahlil qilish va to'g'ri USD ga o'girish"""
    price_obj = item.get("price", {})
    if isinstance(price_obj, dict):
        value = price_obj.get("value")
        currency = price_obj.get("currency")
        if value:
            if currency == "UZS":
                return round(value / USD_RATE)
            elif currency in ["USD", "$"]:
                return int(value)

    params = item.get("params", [])
    for p in params:
        if p.get("key") == "price":
            val = p.get("value", {})
            if isinstance(val, dict):
                num = val.get("value")
                curr = val.get("currency")
                if num:
                    if curr == "UZS":
                        return round(num / USD_RATE)
                    elif curr in ["USD", "$"]:
                        return int(num)
                
                label = str(val.get("label", "")).lower()
                clean_num = ''.join(filter(str.isdigit, label))
                if clean_num:
                    val_num = int(clean_num)
                    if "$" in label or "y.e" in label or "у.е" in label or "usd" in label:
                        return val_num
                    elif val_num > 5000:
                        return round(val_num / USD_RATE)
                    else:
                        return val_num
    return None

def send_telegram(caption, photos):
    valid_photos = []
    for photo in photos[:10]:
        link = photo.get("link", "")
        if link:
            url = link.replace("{width}", "1000").replace("{height}", "750")
            valid_photos.append(url)

    try:
        if len(valid_photos) >= 2:
            media = []
            for idx, photo_url in enumerate(valid_photos):
                if idx == 0:
                    media.append({"type": "photo", "media": photo_url, "caption": caption, "parse_mode": "HTML"})
                else:
                    media.append({"type": "photo", "media": photo_url})
            
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMediaGroup"
            requests.post(url, json={"chat_id": CHANNEL_ID, "media": media}, timeout=15)

        elif len(valid_photos) == 1:
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
            requests.post(url, json={
                "chat_id": CHANNEL_ID,
                "photo": valid_photos[0],
                "caption": caption,
                "parse_mode": "HTML"
            }, timeout=15)

        else:
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
            requests.post(url, json={
                "chat_id": CHANNEL_ID,
                "text": caption,
                "parse_mode": "HTML"
            }, timeout=15)
    except Exception as e:
        print(f"Telegramga yuborishda xatolik: {e}")

def main():
    seen_ids = load_seen_ids()
    post_number = get_next_counter()
    
    try:
        res = cffi_requests.get(
            API_URL,
            impersonate="chrome120",
            headers={
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "uz-UZ,uz;q=0.9,ru;q=0.8",
                "Referer": "https://www.olx.uz/"
            },
            timeout=15
        )
    except Exception as e:
        print(f"OLX ga ulanishda xato: {e}")
        return

    if res.status_code != 200:
        print(f"API xatosi, status: {res.status_code}")
        return

    data = res.json()
    offers = data.get("data", [])
    print(f"OLX'dan jami {len(offers)} ta e'lon olindi.")

    sent_count = 0
    for item in offers:
        item_id = str(item.get("id"))
        
        if item_id in seen_ids:
            continue

        loc_data = item.get("location", {})
        city_name = loc_data.get("city", {}).get("name", "")
        
        # Faqat Toshkent
        if "toshkent" not in city_name.lower() and "ташкент" not in city_name.lower():
            continue

        usd_price = extract_price_in_usd(item)
        
        # Narxni $350 - $1300 oralig'ida qat'iy tekshirish
        if not usd_price or not (350 <= usd_price <= 1300):
            print(f"O'tkazildi (Narx: {usd_price}$ to'g'ri kelmadi): ID {item_id}")
            continue

        title = item.get("title", "Yangi e'lon")
        description = item.get("description", "")
        params = item.get("params", [])
        
        rooms = "2"
        area = "Ko'rsatilmagan"
        floor = "Ko'rsatilmagan"

        for p in params:
            key = p.get("key")
            val = p.get("value", {})
            if key in ["number_of_rooms", "number_of_rooms_string"]:
                rooms = val.get("label", "2") if isinstance(val, dict) else "2"
            elif key in ["total_area", "total_area_string"]:
                area = val.get("label", "Ko'rsatilmagan") if isinstance(val, dict) else "Ko'rsatilmagan"
            elif key == "floor":
                floor = val.get("label", "Ko'rsatilmagan") if isinstance(val, dict) else "Ko'rsatilmagan"

        price_str = f"{usd_price}$"
        district_name = loc_data.get("district", {}).get("name", "")
        location_str = f"{city_name}, {district_name}".strip(", ")

        user_data = item.get("user", {})
        user_name = user_data.get("name", "E'lon egasi")

        mos_keladi_str = parse_target_audience(f"{title} {description}")
        phone_number = get_phone_number(item_id)
        photos = item.get("photos", [])

        caption = (
            f"🏠 <b>{rooms} xonali kvartira</b> ({title})\n"
            f"📍 <b>Manzil:</b> {location_str}\n\n"
            f"📐 <b>Maydon:</b> {area}\n"
            f"🏢 <b>Qavat:</b> {floor}\n"
            f"🛋 <b>Mebellar:</b> To‘liq jihozlangan\n"
            f"✨ <b>Ta'mir:</b> Yevro remont\n"
            f"✅ <b>Barcha sharoitlar mavjud</b>\n\n"
            f"👨‍👩‍👧 <b>Mos keladi:</b>\n"
            f"{mos_keladi_str}\n\n"
            f"💵 <b>Narx:</b> {price_str}\n"
            f"📞 <b>Tel:</b> {phone_number}\n"
            f"👤 <b>E'lon egasi:</b> {user_name}\n\n"
            f"⚡️ Joylashuvi juda qulay va infratuzilma rivojlangan\n\n"
            f"📸 <b>INSTAGRAM:</b> <a href='{INSTAGRAM_LINK}'>toshkent_ijaraga</a>\n"
            f"📩 <b>TELEGRAM:</b> @turayev_bek\n\n"
            f"#id_{post_number}"
        )

        send_telegram(caption, photos)
        save_seen_id(item_id)
        post_number += 1
        save_counter(post_number)
        sent_count += 1
        print(f"Muvaffaqiyatli yuborildi: #{item_id} | Narxi: {usd_price}$ | ID: #id_{post_number - 1}")

        if sent_count >= 5:
            break

    if sent_count == 0:
        print("Yangi mos keladigan e'lonlar topilmadi.")

if __name__ == "__main__":
    main()
