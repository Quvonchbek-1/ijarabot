import os
import sqlite3
import asyncio
from aiogram import Bot, Dispatcher, html
from aiogram.filters import CommandStart, CommandObject
from aiogram.types import Message

BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

def get_offer(offer_id):
    try:
        conn = sqlite3.connect('housing.db')
        cursor = conn.cursor()
        cursor.execute('SELECT title, phone, price, location FROM offers WHERE offer_id = ?', (str(offer_id),))
        result = cursor.fetchone()
        conn.close()
        return result
    except Exception as e:
        print(f"Baza xatosi: {e}")
        return None

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
            await message.answer("❌ Kechirasiz, ushbu e'lon eskirgan yoki topilmadi.")
    else:
        await message.answer("Xush kelibsiz! Kanaldagi e'lonlar telefon raqamini olish uchun e'londagi tugmani bosing.")

async def main():
    print("🤖 Bot ishga tushdi va xabarlarni kutmoqda...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
