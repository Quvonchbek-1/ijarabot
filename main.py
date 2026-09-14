import os
import re
import asyncio
import requests
from curl_cffi import requests as cffi_requests

from aiogram import Bot, Dispatcher, html
from aiogram.filters import CommandStart, CommandObject
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

from database import init_db, save_offer, get_offer

BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
CHANNEL_ID = os.environ.get("CHANNEL_ID", "").strip()
BOT_USERNAME = os.environ.get("BOT_USERNAME", "").strip()

API_URL = "https://www.olx.uz/api/v1/offers/?offset=0&limit=40"
SEEN_FILE = "seen_ids.txt"
INSTAGRAM_LINK = "https://www.instagram.com/toshkent_ijaraga"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

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
        res = cffi_requests.get(phone_url, impersonate="chrome120", timeout=10)
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
        print(f"Tel olishda xatosi ({item_id}): {e}")
    return "Ko'rsatilmagan"

# --- TELEGRAM BOT TUGMA HANDLERI ---
@dp.message(CommandStart())
async def start_handler(message: Message, command: CommandObject):
    args = command.args
    if args and args.startswith("offer_"):
        offer_id = args.replace("offer_", "").strip()
        data = get_offer(offer_id)
        
        if data:
            title, phone, price, location = data
            phone_text = f"<code>{phone}</code>" if phone != "Ko'rsatilmagan" else "E'londa ko'rsatilmagan"
            text = (
                f"🏠 <b>E'lon:</b> {html.quote(title)}\n"
                f"📍 <b>Manzil:</b> {location}\n"
                f"💵 <b>Narx:</b> {price}\n\n"
                f"📞 <b>Telefon raqam:</b> {phone_text}"
            )
            await message.answer(text, parse_mode="HTML")
        else:
            await message.answer("❌ Kechirasiz, ushbu e'lon bo'yicha ma'lumot topilmadi yoki eskirgan.")
    else:
        await message.answer("Xush kelibsiz! Kanaldagi e'lonlar telefon raqamini olish uchun e'londagi tugmani bosing.")

# --- SCRAPER FUNTSIYASI ---
async def run_scraper():
    seen_ids = load_seen_ids()
    print("🌐 OLX'dan yangi e'lonlar tekshirilmoqda...")

    try:
        res = cffi_requests.get(API_URL, impersonate="chrome120", timeout=20)
        if res.status_code != 200:
            return
        offers = res.json().get("data", [])
    except Exception as e:
        print(f"OLX API xatosi: {e}")
        return

    for item in offers:
        item_id = str(item.get("id", ""))
        if not item_id or item_id in seen_ids:
            continue

        title = item.get("title", "")
        title_lower = title.lower()

        # Faqat Toshkent va Uy-joy e'lonlari
        location_data = item.get("location", {})
        city_name = location_data.get("city", {}).get("name", "") if isinstance(location_data, dict) else ""
        if "toshkent" not in city_name.lower() and "ташкент" not in city_name.lower():
            continue

        if any(w in title_lower for w in ["sutka", "сутки", "sutkaga", "kunlik"]):
            continue

        # Narx va ma'lumotlar
        price_obj = item.get("price", {})
        price_val = price_obj.get("value", 0) if isinstance(price_obj, dict) else 0
        price_curr = price_obj.get("currency", "USD") if isinstance(price_obj, dict) else "USD"
        price_str = f"{price_val} {price_curr}" if price_val else "Kelishilgan holda"

        district_name = location_data.get("district", {}).get("name", "") if isinstance(location_data, dict) else ""
        location_str = f"{city_name}, {district_name}".strip(", ")

        phone = get_phone_number(item_id)
        save_offer(item_id, title, phone, price_str, location_str)

        # Telegramga kanal posti
        deep_link = f"https://t.me/{BOT_USERNAME}?start=offer_{item_id}"
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🔓 Telefon raqamini ko'rish", url=deep_link)
        ]])

        caption = (
            f"🏠 <b>{title}</b>\n"
            f"📍 <b>Manzil:</b> {location_str}\n\n"
            f"💵 <b>Narx:</b> {price_str}\n"
            f"📞 <b>Tel:</b> +998 90 *** ** **\n\n"
            f"📸 <b>INSTAGRAM:</b> <a href='{INSTAGRAM_LINK}'>toshkent_ijaraga</a>"
        )

        photos = item.get("photos", [])
        valid_photo = photos[0].get("link", "").replace("{width}", "1000").replace("{height}", "750") if photos else None

        try:
            if valid_photo:
                await bot.send_photo(chat_id=CHANNEL_ID, photo=valid_photo, caption=caption, parse_mode="HTML", reply_markup=keyboard)
            else:
                await bot.send_message(chat_id=CHANNEL_ID, text=caption, parse_mode="HTML", reply_markup=keyboard)

            save_seen_id(item_id)
            seen_ids.add(item_id)
            print(f"✅ Kanalga joylandi: {title[:30]}")
            await asyncio.sleep(3)
        except Exception as e:
            print(f"Kanalga yuborishda xato: {e}")

async def scraper_loop():
    while True:
        await run_scraper()
        await asyncio.sleep(900)  # Har 15 daqiqada bir marta ishlaydi

async def main():
    init_db()
    # Scraper va Botni bir vaqtda 24/7 ishlatish
    asyncio.create_task(scraper_loop())
    print("🚀 Bot va Scraper bir vaqtda ishga tushdi!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
