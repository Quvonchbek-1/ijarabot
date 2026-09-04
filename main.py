import os
import requests
from curl_cffi import requests as cffi_requests

BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
CHANNEL_ID = os.environ.get("CHANNEL_ID", "").strip()

# OLX Tashkent kvartiralar ijarasi ichki API-si
API_URL = "https://www.olx.uz/api/v1/offers/?offset=0&limit=10&category_id=1121"
SEEN_FILE = "seen_ids.txt"

def load_seen_ids():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE, "r") as f:
            return set(line.strip() for line in f if line.strip())
    return set()

def save_seen_id(item_id):
    with open(SEEN_FILE, "a") as f:
        f.write(f"{item_id}\n")

def send_telegram(title, price, link, photo_url=None):
    caption = f"🏠 <b>{title}</b>\n\n💰 <b>Narxi:</b> {price}\n\n🔗 <a href='{link}'>OLX-da ko'rish</a>"
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/" + ("sendPhoto" if photo_url else "sendMessage")
    payload = {"chat_id": CHANNEL_ID, "caption" if photo_url else "text": caption, "parse_mode": "HTML"}
    if photo_url:
        payload["photo"] = photo_url
    
    res = requests.post(url, json=payload)
    print(f"Telegram javobi: {res.status_code}")

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
    print(f"API Javob kodi: {res.status_code}")
    
    if res.status_code != 200:
        print("API ga ulanib bo'lmadi")
        return

    data = res.json()
    offers = data.get("data", [])
    print(f"Topilgan e'lonlar soni: {len(offers)}")

    for item in offers[:5]:
        item_id = str(item.get("id"))
        if item_id in seen_ids:
            continue

        title = item.get("title", "Yangi e'lon")
        link = item.get("url", "")
        
        params = item.get("params", [])
        price = "Ko'rsatilmagan"
        for p in params:
            if p.get("key") == "price":
                price = p.get("value", {}).get("label", "Ko'rsatilmagan")
                break

        photos = item.get("photos", [])
        photo_url = None
        if photos:
            photo_url = photos[0].get("link", "").replace("{width}", "1000").replace("{height}", "750")

        send_telegram(title, price, link, photo_url)
        save_seen_id(item_id)
        print(f"Yangi e'lon joylandi: {title}")

if __name__ == "__main__":
    main()
