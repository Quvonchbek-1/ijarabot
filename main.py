import os
from curl_cffi import requests
from bs4 import BeautifulSoup

BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
CHANNEL_ID = os.environ.get("CHANNEL_ID", "").strip()

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
    
    res = requests.post(url, json=payload, impersonate="chrome120")
    print(f"Telegram javobi: {res.status_code}")

def main():
    seen_ids = load_seen_ids()
    
    # Chrome 120 brauzerining TLS barmoq izini simulyatsiya qilish
    res = requests.get(
        OLX_URL,
        impersonate="chrome120",
        headers={
            "Accept-Language": "uz-UZ,uz;q=0.9,ru;q=0.8,en;q=0.7",
            "Referer": "https://www.olx.uz/",
        }
    )
    print(f"OLX Javob kodi: {res.status_code}")
    
    if res.status_code != 200:
        print("OLX sahifasiga ulanib bo'lmadi")
        return

    soup = BeautifulSoup(res.text, "html.parser")
    cards = soup.find_all("div", {"data-cy": "l-card"})
    print(f"Topilgan e'lonlar soni: {len(cards)}")

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
