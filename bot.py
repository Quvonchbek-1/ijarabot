import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from database import get_offer, is_user_subscribed

BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    args = context.args

    if args and args[0].startswith("offer_"):
        offer_id = args[0].replace("offer_", "")
        offer = get_offer(offer_id)

        if not offer:
            await update.message.reply_text("❌ Ushbu e'lon topilmadi yoki eskirgan.")
            return

        title, phone, price, location = offer

        if is_user_subscribed(user_id):
            text = (
                f"✅ <b>E'lon tafsilotlari:</b>\n\n"
                f"🏠 {title}\n"
                f"📍 Manzil: {location}\n"
                f"💵 Narxi: {price}$\n\n"
                f"📞 <b>Tel:</b> <a href='tel:{phone}'>{phone}</a>"
            )
            await update.message.reply_text(text, parse_mode="HTML")
        else:
            text = (
                f"🔒 <b>Ushbu e'lon raqami yopiq!</b>\n\n"
                f"E'lon egasi raqamini va to'liq ma'lumotlarni ko'rish uchun VIP obunasini faollashtiring.\n\n"
                f"💳 <b>Obuna narxi:</b> 30,000 so'm / oy"
            )
            keyboard = [
                [InlineKeyboardButton("💳 VIP Obuna sotib olish (Click/Payme)", callback_data="buy_sub")]
            ]
            await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    else:
        await update.message.reply_text("Xush kelibsiz! Kanalimizdagi e'lonlar orqali bog'lanishingiz mumkin.")

if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    print("Bot ishga tushdi...")
    app.run_polling()
