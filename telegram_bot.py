import asyncio
import logging
import os
import re
from datetime import datetime
from threading import Thread

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import LabeledPrice, PreCheckoutQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.storage.memory import MemoryStorage
from flask import Flask
from dotenv import load_dotenv

import database as db  # ← ОБЩАЯ БАЗА ДАННЫХ

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_IDS = [int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]
STARS_PRICE = 50

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# ===== ВЕБ-СЕРВЕР ДЛЯ RENDER =====
flask_app = Flask(__name__)

@flask_app.route('/')
def health_check():
    return "✅ Telegram bot is alive!", 200

def run_flask():
    flask_app.run(host='0.0.0.0', port=8081)  # ← другой порт для Telegram

Thread(target=run_flask, daemon=True).start()
print("🌐 Веб-сервер Telegram запущен на порту 8081")

# ===== КОМАНДЫ =====

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐ Купить Premium", callback_data="buy")],
        [InlineKeyboardButton(text="📖 Инструкция", callback_data="help")]
    ])
    
    await message.answer(
        "⚖️ *Lawyer Pay Bot*\n\n"
        "Оплатите премиум и получите безлимитные запросы в Discord боте!\n\n"
        f"💰 Цена: {STARS_PRICE} Stars (~84 ₽)\n"
        f"📅 Срок: 30 дней\n\n"
        "После оплаты напишите в Discord боте `/status` — подписка будет активна!",
        parse_mode="Markdown",
        reply_markup=keyboard
    )

@dp.callback_query(F.data == "buy")
async def buy_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    
    await bot.send_invoice(
        chat_id=user_id,
        title="Premium доступ 30 дней",
        description="Безлимитные запросы к УК и ПК",
        payload=f"premium_{user_id}_{int(datetime.now().timestamp())}",
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(label="30 дней", amount=STARS_PRICE)],
        start_parameter="premium"
    )
    await callback.answer()

@dp.callback_query(F.data == "help")
async def help_callback(callback: types.CallbackQuery):
    await callback.message.answer(
        "📖 *Инструкция:*\n\n"
        "1️⃣ Нажмите «Купить Premium»\n"
        "2️⃣ Оплатите Stars\n"
        "3️⃣ **Напишите в Discord боте команду `/status`**\n\n"
        "✅ Если оплата прошла, статус покажет активную подписку!\n\n"
        "❓ Вопросы: @ваш_ник",
        parse_mode="Markdown"
    )
    await callback.answer()

@dp.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery):
    await bot.answer_pre_checkout_query(query.id, ok=True)

@dp.message(F.successful_payment)
async def successful_payment(message: types.Message):
    payment = message.successful_payment
    user_name = message.from_user.full_name
    total_amount = payment.total_amount
    
    logging.info(f"💰 Платёж от {user_name}: {total_amount} Stars")
    
    await message.answer(
        f"✅ *Оплата прошла успешно!*\n\n"
        f"⭐ Спасибо!\n\n"
        f"📌 **Важно:** Ваш Discord ID не привязан автоматически.\n"
        f"Напишите владельцу бота ваш **Discord ID**, чтобы активировать премиум.\n\n"
        f"Или дождитесь ручной активации.",
        parse_mode="Markdown"
    )
    
    # Уведомление админам
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                f"🎉 Новая покупка!\n"
                f"👤 {user_name}\n"
                f"💰 {total_amount} Stars\n\n"
                f"Спросите у пользователя его **Discord ID** и выполните в Discord боте:\n"
                f"`/give @его_ник 30`",
                parse_mode="Markdown"
            )
        except:
            pass

# ===== ЗАПУСК =====
async def main():
    logging.basicConfig(level=logging.INFO)
    print("🚀 Telegram бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
