from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

BOT_USERNAME = "UyJoyRaqamBot"  # O'zingizning botingiz username'i (@'siz)

async def post_to_channel(bot: Bot, channel_id: str, offer_id: str, title: str, price: str, photo_url: str):
    # Deep link tugmasini yaratamiz
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="📞 Telefon raqamini ko'rish", 
                url=f"https://t.me/{BOT_USERNAME}?start=phone_{offer_id}"
            )
        ]
    ])

    caption = (
        f"🏠 <b>{title}</b>\n\n"
        f"💰 <b>Narxi:</b> {price}\n\n"
        f"👇 Telefon raqamini olish uchun pastdagi tugmani bosing:"
    )

    await bot.send_photo(
        chat_id=channel_id,
        photo=photo_url,
        caption=caption,
        parse_mode="HTML",
        reply_markup=keyboard
    )
