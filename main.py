import os
import requests
from curl_cffi import requests as cffi_requests

BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
CHANNEL_ID = os.environ.get("CHANNEL_ID", "").strip()

API_URL = "https://www.olx.uz/api/v1/offers/?offset=0&limit=10&query=ijara"
SEEN_FILE = "seen_ids.txt"
USD_RATE = 12800  # 1 USD uchun taxminiy so'm kursi

def load_seen_ids():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE, "r") as f:
            return set(line.strip() for line in f if line.strip())
    return set()

def save_seen_id(item_id):
    with open(SEEN_FILE, "a") as f:
        f.write(f"{item_id}\n")

def send_telegram_media_group(caption, photos):
    # Maksimum 10 ta rasm albom ko'rinishida yuboriladi
    media = []
    for idx, photo in enumerate(photos[:10]):
        photo_url = photo.get("link", "").replace("{width}", "1000").replace("{height}", "750")
        if idx == 0:
            media.append({"type": "photo", "media": photo_url, "caption": caption, "parse_mode": "HTML"})
        else:
            media.append({"type": "photo", "media": photo_url})

    if media:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMediaGroup"
        res = requests.post(url, json={"chat_id": CHANNEL_ID, "media": media})
    else:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        res = requests.post(url, json={"chat_id": CHANNEL_ID, "text": caption, "parse_mode": "HTML"})
    
    print(f"Telegram yuborish holati: {res.status_code}")

def main():
    seen_ids = load_seen_ids()
    
    res = cffi_requests.get(
        API_URL,
        impersonate="chrome120",
        headers={
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "uz-UZ,uz;q=0.9,ru;q=0.8",
            "Referer": "https://www.olx.uz/"
        }
    )
    
    if res.status_code != 200:
        print("API ga ulanib bo'lmadi")
        return

    data = res.json()
    offers = data.get("data", [])

    for item in offers[:5]:
        item_id = str(item.get("id"))
        if item_id in seen_ids:
            continue

        title = item.get("title", "Yangi e'lon")
        link = item.get("url", "")
        
        params = item.get("params", [])
        price_str = "Ko'rsatilmagan"
        rooms = "Ko'rsatilmagan"
        area = "Ko'rsatilmagan"
        floor = "Ko'rsatilmagan"

        for p in params:
            key = p.get("key")
            val = p.get("value", {})
            label = val.get("label", "Ko'rsatilmagan") if isinstance(val, dict) else "Ko'rsatilmagan"

            if key == "price":
                num = val.get("value") if isinstance(val, dict) else None
                curr = val.get("currency") if isinstance(val, dict) else None
                if num:
                    if curr == "UZS":
                        usd_val = round(num / USD_RATE)
                        price_str = f"${usd_val:,} ({num:,} so'm)"
                    elif curr == "USD":
                        price_str = f"${num:,}"
                    else:
                        price_str = f"{num} {curr}"
                else:
                    price_str = label
            elif key in ["number_of_rooms", "number_of_rooms_string"]:
                rooms = label
            elif key in ["total_area", "total_area_string"]:
                area = label
            elif key == "floor":
                floor = label

        loc_data = item.get("location", {})
        city_name = loc_data.get("city", {}).get("name", "Toshkent")
        district_name = loc_data.get("district", {}).get("name", "")
        location_str = f"{city_name}, {district_name}".strip(", ")

        user_data = item.get("user", {})
        user_name = user_data.get("name", "E'lon egasi")

        photos = item.get("photos", [])

        caption = (
            f"🏠 <b>{title}</b>\n\n"
            f"💰 <b>Narxi:</b> {price_str}\n"
            f"🚪 <b>Xonalar soni:</b> {rooms}\n"
            f"📐 <b>Maydoni:</b> {area}\n"
            f"🏢 <b>Qavat:</b> {floor}\n"
            f"📍 <b>Manzil:</b> {location_str}\n"
            f"👤 <b>E'lon egasi:</b> {user_name}\n\n"
            f"🔗 <a href='{link}'>E'lon va bog'lanish havolasi</a>"
        )

        send_telegram_media_group(caption, photos)
        save_seen_id(item_id)
        print(f"Yangi e'lon yuborildi: {title}")

if __name__ == "__main__":
    main()
