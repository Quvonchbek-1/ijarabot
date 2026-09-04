import os
import requests
from curl_cffi import requests as cffi_requests

BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
CHANNEL_ID = os.environ.get("CHANNEL_ID", "").strip()

# Toshkent shahri ijaraga kvartiralar API adresi
API_URL = "https://www.olx.uz/api/v1/offers/?offset=0&limit=10&query=ijara"
SEEN_FILE = "seen_ids.txt"

def load_seen_ids():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE, "r") as f:
            return set(line.strip() for line in f if line.strip())
    return set()

def save_seen_id(item_id):
    with open(SEEN_FILE, "a") as f:
        f.write(f"{item_id}\n")

def send_telegram(caption, photo_url=None):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/" + ("sendPhoto" if photo_url else "sendMessage")
    payload = {
        "chat_id": CHANNEL_ID, 
        "caption" if photo_url else "text": caption, 
        "parse_mode": "HTML"
    }
    if photo_url:
        payload["photo"] = photo_url
    
    res = requests.post(url, json=payload)
    print(f"Telegram yuborish holati: {res.status_code} - {res.text}")

def main():
    seen_ids = load_seen_ids()
    print(f"Bazada bor IDlar soni: {len(seen_ids)}")
    
    res = cffi_requests.get(
        API_URL,
        impersonate="chrome120",
        headers={
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "uz-UZ,uz;q=0.9,ru;q=0.8",
            "Referer": "https://www.olx.uz/"
        }
    )
    print(f"OLX API javob kodi: {res.status_code}")
    
    if res.status_code != 200:
        print("API ga ulanishda xatolik bo'ldi")
        return

    data = res.json()
    offers = data.get("data", [])
    print(f"OLX dan kelgan e'lonlar soni: {len(offers)}")

    sent_count = 0
    for item in offers[:5]:
        item_id = str(item.get("id"))
        
        if item_id in seen_ids:
            print(f"E'lon {item_id} ilgari yuborilgan, o'tkazib yuborildi.")
            continue

        title = item.get("title", "Yangi e'lon")
        
        params = item.get("params", [])
        price = "Ko'rsatilmagan"
        rooms = "Ko'rsatilmagan"
        area = "Ko'rsatilmagan"
        floor = "Ko'rsatilmagan"

        for p in params:
            key = p.get("key")
            val = p.get("value", {}).get("label", "Ko'rsatilmagan")
            if key == "price":
                price = val
            elif key in ["number_of_rooms", "number_of_rooms_string"]:
                rooms = val
            elif key in ["total_area", "total_area_string"]:
                area = val
            elif key == "floor":
                floor = val

        loc_data = item.get("location", {})
        city_name = loc_data.get("city", {}).get("name", "Toshkent")
        district_name = loc_data.get("district", {}).get("name", "")
        location_str = f"{city_name}, {district_name}".strip(", ")

        user_data = item.get("user", {})
        user_name = user_data.get("name", "E'lon egasi")

        photos = item.get("photos", [])
        photo_url = None
        if photos:
            photo_url = photos[0].get("link", "").replace("{width}", "1000").replace("{height}", "750")

        caption = (
            f"🏠 <b>{title}</b>\n\n"
            f"💰 <b>Narxi:</b> {price}\n"
            f"🚪 <b>Xonalar soni:</b> {rooms}\n"
            f"📐 <b>Maydoni:</b> {area}\n"
            f"🏢 <b>Qavat:</b> {floor}\n"
            f"📍 <b>Manzil:</b> {location_str}\n"
            f"👤 <b>E'lon egasi:</b> {user_name}"
        )

        send_telegram(caption, photo_url)
        save_seen_id(item_id)
        sent_count += 1
        print(f"Yangi e'lon yuborildi: {title}")

    print(f"Jami yuborilgan yangi e'lonlar: {sent_count}")

if __name__ == "__main__":
    main()
