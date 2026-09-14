import logging
from aiogram import Bot, Dispatcher, html
from aiogram.filters import CommandStart, CommandObject
from aiogram.types import Message
from database import get_phone_number, init_db

BOT_TOKEN = "YOUR_BOT_TOKEN"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

@dp.message(CommandStart())
async def start_handler(message: Message, command: CommandObject):
    args = command.args  # Masalan: "phone_123456"
    
    if args and args.startswith("phone_"):
        offer_id = args.split("phone_")[1]
        data = get_phone_number(offer_id)
        
        if data:
            title, phone = data
            response_text = (
                f"📌 <b>E'lon:</b> {html.quote(title)}\n\n"
                f"📞 <b>Telefon raqam:</b> <code>{phone}</code>\n\n"
                f"<i>E'lon egasi bilan bog'lanishingiz mumkin.</i>"
            )
            await message.answer(response_text, parse_mode="HTML")
        else:
            await message.answer("❌ Kechirasiz, ushbu e'lon bo'yicha telefon raqami topilmadi yoki eskirgan.")
    else:
        await message.answer(
            "Xush kelibsiz! 🏠\nKanalimizdagi e'lonlarning telefon raqamlarini olish uchun e'londagi tugmani bosing."
        )

if __name__ == "__main__":
    init_db()
    import asyncio
    asyncio.run(dp.start_polling(bot))
