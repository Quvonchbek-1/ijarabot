import os
import requests
from bs4 import BeautifulSoup

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHANNEL_ID = os.environ.get("CHANNEL_ID")

# O'zingizga kerakli OLX bo'limi havolasini qo'ying (Masalan: Toshkent uy ijara bo'limi)
OLX_URL = "https://www.olx.uz/d/oz/nedvizhimost/kvartiry/dolgosrochnaya-arenda-kvartir/tashkent/"
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
    if photo_url:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
        payload = {"chat_id": CHANNEL_ID, "photo": photo_url, "caption": caption, "parse_mode": "HTML"}
    else:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = {"chat_id": CHANNEL_ID, "text": caption, "parse_mode": "HTML"}
    
    requests.post(url, json=payload)

def main():
    seen_ids = load_seen_ids()
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    res = requests.get(OLX_URL, headers=headers)
    
    if res.status_code != 200:
        print("OLX sahifasiga ulanib bo'lmadi")
        return

    soup = BeautifulSoup(res.text, "html.parser")
    cards = soup.find_all("div", {"data-cy": "l-card"})

    for card in cards[:5]:
        link_tag = card.find("a", href=True)
        if not link_tag:
            continue
        
        href = link_tag["href"]
        link = "https://www.olx.uz" + href if href.startswith("/") else href
        item_id = card.get("id", link)

        if str(item_id) in seen_ids:
            continue

        title_tag = card.find("h6") or card.find("h4")
        title = title_tag.text.strip() if title_tag else "Yangi e'lon"

        price_tag = card.find("p", {"data-testid": "ad-price"})
        price = price_tag.text.strip() if price_tag else "Ko'rsatilmagan"

        img_tag = card.find("img")
        photo_url = img_tag["src"] if img_tag and "src" in img_tag.attrs else None

        send_telegram(title, price, link, photo_url)
        save_seen_id(item_id)
        print(f"Yangi e'lon joylandi: {title}")

if __name__ == "__main__":
    main()
