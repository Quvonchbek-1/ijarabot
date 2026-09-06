import os
import requests
from curl_cffi import requests as cffi_requests

BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
CHANNEL_ID = os.environ.get("CHANNEL_ID", "").strip()

API_URL = "https://www.olx.uz/api/v1/offers/?offset=0&limit=10&query=ijara"
SEEN_FILE = "seen_ids.txt"
COUNTER_FILE = "counter.txt"
USD_RATE = 12800

def load_seen_ids():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE, "r") as f:
            return set(line.strip() for line in f if line.strip())
    return set()

def save_seen_id(item_id):
    with open(SEEN_FILE, "a") as f:
        f.write(f"{item_id}\n")

def get_next_counter():
    if os.path.exists(COUNTER_FILE):
        with open(COUNTER_FILE, "r") as f:
            try:
                return int(f.read().strip())
            except ValueError:
                return 1
    return 1

def save_counter(count):
    with open(COUNTER_FILE, "w") as f:
        f.write(str(count))

def send_telegram(caption, photos):
    valid_photos = []
    for photo in photos[:10]:
        link = photo.get("link", "")
        if link:
            url = link.replace("{width}", "1000").replace("{height}", "750")
            valid_photos.append(url)

    if len(valid_photos) >= 2:
        media = []
        for idx, photo_url in enumerate(valid_photos):
            if idx == 0:
                media.append({"type": "photo", "media": photo_url, "caption": caption, "parse_mode": "HTML"})
            else:
                media.append({"type": "photo", "media": photo_url})
        
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMediaGroup"
        requests.post(url, json={"chat_id": CHANNEL_ID, "media": media})

    elif len(valid_photos) == 1:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
        requests.post(url, json={
            "chat_id": CHANNEL_ID,
            "photo": valid_photos[0],
            "caption": caption,
            "parse_mode": "HTML"
        })

    else:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        requests.post(url, json={
            "chat_id": CHANNEL_ID,
            "text": caption,
            "parse_mode": "HTML"
        })

def main():
    seen_ids = load_seen_ids()
    post_number = get_next_counter()
    
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
        
        params = item.get("params", [])
        price_str = "Kelishilgan holda"
        rooms = "2"
        area = "Ko'rsatilmagan"
        floor = "Ko'rsatilmagan"

        for p in params:
            key = p.get("key")
            val = p.get("value", {})

            if key == "price":
                num = val.get("value") if isinstance(val, dict) else None
                curr = val.get("currency") if isinstance(val, dict) else None
                if num:
                    if curr == "UZS":
                        usd_val = round(num / USD_RATE)
                        price_str = f"{usd_val}$"
                    else:
                        price_str = f"{num}$"
                else:
                    label = val.get("label", "") if isinstance(val, dict) else ""
                    clean_num = ''.join(filter(str.isdigit, str(label)))
                    if clean_num:
                        price_str = f"{clean_num}$"
                    else:
                        price_str = "Kelishilgan holda"
            elif key in ["number_of_rooms", "number_of_rooms_string"]:
                rooms = val.get("label", "2") if isinstance(val, dict) else "2"
            elif key in ["total_area", "total_area_string"]:
                area = val.get("label", "Ko'rsatilmagan") if isinstance(val, dict) else "Ko'rsatilmagan"
            elif key == "floor":
                floor = val.get("label", "Ko'rsatilmagan") if isinstance(val, dict) else "Ko'rsatilmagan"

        loc_data = item.get("location", {})
        city_name = loc_data.get("city", {}).get("name", "Toshkent")
        district_name = loc_data.get("district", {}).get("name", "")
        location_str = f"{city_name}, {district_name}".strip(", ")

        photos = item.get("photos", [])

        caption = (
            f"🏠 <b>{rooms} xonali kvartira</b> ({title})\n"
            f"📍 <b>Manzil:</b> {location_str}\n"
            f"🚇 <b>Joylashuvi:</b> Metro va transportga juda yaqin\n\n"
            f"📐 <b>Maydon:</b> {area}\n"
            f"🏢 <b>Qavat:</b> {floor}\n"
            f"🛋 <b>Mebellar:</b> To‘liq jihozlangan\n"
            f"✨ <b>Ta'mir:</b> Yevro remont\n"
            f"✅ <b>Barcha sharoitlar mavjud</b>\n\n"
            f"👨‍👩‍👧 <b>Mos keladi:</b>\n"
            f"• Oilaga\n"
            f"• Talaba qizlarga\n"
            f"• Ishchi yigitlarga\n\n"
            f"💵 <b>Narx:</b> {price_str}\n\n"
            f"⚡️ Joylashuvi juda qulay va infratuzilma rivojlangan\n\n"
            f"📩 <b>Murojaat uchun yozing :</b> @turayev_bek\n\n"
            f"#{post_number}"
        )

        send_telegram(caption, photos)
        save_seen_id(item_id)
        post_number += 1
        save_counter(post_number)
        print(f"Yangi e'lon yuborildi: #{post_number - 1}")

if __name__ == "__main__":
    main()
