import asyncio
import logging
import os
from datetime import datetime
from threading import Thread

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import LabeledPrice, InlineKeyboardMarkup, InlineKeyboardButton, PreCheckoutQuery
from aiogram.fsm.storage.memory import MemoryStorage
from flask import Flask
from dotenv import load_dotenv
import aiohttp

import database as db

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
    port = int(os.environ.get("PORT", 8081))
    flask_app.run(host='0.0.0.0', port=port)

Thread(target=run_flask, daemon=True).start()
print("🌐 Веб-сервер Telegram бота запущен")

# ===== КОМАНДЫ =====

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"⭐ Купить Premium ({STARS_PRICE} Stars)", callback_data="buy")],
        [InlineKeyboardButton(text="🔗 Привязать Discord ID", callback_data="link")],
        [InlineKeyboardButton(text="📖 Инструкция", callback_data="help")]
    ])
    
    await message.answer(
        "⚖️ *Lawyer Pay Bot*\n\n"
        "💎 *Что нужно сделать:*\n"
        "1️⃣ Привяжите ваш Discord ID\n"
        "2️⃣ Купите Premium\n"
        "3️⃣ После оплаты премиум активируется автоматически!\n\n"
        f"💰 Цена: {STARS_PRICE} Stars (~84 ₽)\n"
        f"📅 Срок: 30 дней",
        parse_mode="Markdown",
        reply_markup=keyboard
    )

@dp.callback_query(F.data == "link")
async def link_prompt(callback: types.CallbackQuery):
    await callback.message.answer(
        "🔗 *Привязка Discord ID*\n\n"
        "1. Откройте Discord\n"
        "2. Настройки → Дополнительно → Режим разработчика\n"
        "3. ПКМ по своему имени → Копировать ID\n"
        "4. Введите: `/link 123456789012345678`",
        parse_mode="Markdown"
    )
    await callback.answer()

@dp.message(Command("link"))
async def link_account(message: types.Message):
    args = message.text.split()
    if len(args) != 2:
        await message.answer("❌ Использование: `/link 123456789012345678`", parse_mode="Markdown")
        return
    
    discord_id = args[1]
    telegram_id = str(message.from_user.id)
    
    if db.is_premium(discord_id):
        await message.answer(f"✅ Discord ID `{discord_id}` уже имеет активную подписку!", parse_mode="Markdown")
    else:
        db.link_accounts(discord_id, telegram_id)
        await message.answer(f"✅ Discord ID `{discord_id}` привязан!\nТеперь купите Premium.", parse_mode="Markdown")

@dp.callback_query(F.data == "buy")
async def buy_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    telegram_id = str(user_id)
    
    discord_id = db.get_discord_id_by_telegram(telegram_id)
    if not discord_id:
        await callback.message.answer("❌ *Сначала привяжите Discord ID!*\nИспользуйте `/link 123456789`", parse_mode="Markdown")
        await callback.answer()
        return
    
    await bot.send_invoice(
        chat_id=user_id,
        title="Premium доступ 30 дней",
        description=f"Активация для Discord ID: {discord_id}",
        payload=f"premium_{discord_id}_{telegram_id}_{int(datetime.now().timestamp())}",
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
        "1️⃣ `/link 123456789` — привязать Discord ID\n"
        "2️⃣ Нажмите «Купить Premium»\n"
        "3️⃣ Оплатите Stars\n"
        "4️⃣ Premium активируется автоматически!\n\n"
        "📌 *Discord ID:* Настройки Discord → Дополнительно → Режим разработчика → ПКМ по имени → Копировать ID",
        parse_mode="Markdown"
    )
    await callback.answer()

@dp.message(Command("balance"))
async def get_balance(message: types.Message):
    """Показать баланс Stars у бота (только для администратора)"""
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("❌ У вас нет прав для просмотра баланса.")
        return
    
    # Отправляем прямой запрос к Telegram API (работает всегда)
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getMyStarBalance"
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url) as response:
                result = await response.json()
                
                if result.get("ok"):
                    star_balance = result["result"]["star_amount"]
                    await message.answer(
                        f"💰 *Баланс Звёзд у бота:* **{star_balance}** ⭐\n\n"
                        f"📊 *Статистика:*\n"
                        f"• Цена подписки: {STARS_PRICE} Stars\n"
                        f"• Можно выдать ≈ {star_balance // STARS_PRICE} подписок",
                        parse_mode="Markdown"
                    )
                else:
                    await message.answer(f"❌ Ошибка: {result.get('description', 'Неизвестная ошибка')}")
        except Exception as e:
            await message.answer(f"❌ Ошибка соединения: {e}")

@dp.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery):
    await bot.answer_pre_checkout_query(query.id, ok=True)

@dp.message(F.successful_payment)
async def successful_payment(message: types.Message):
    payment = message.successful_payment
    user_name = message.from_user.full_name
    total_amount = payment.total_amount
    payload = payment.invoice_payload
    
    parts = payload.split('_')
    if len(parts) >= 2:
        discord_id = parts[1]
    else:
        await message.answer("❌ Ошибка: не удалось определить Discord ID")
        return
    
    db.set_premium(discord_id, 30, str(message.from_user.id))
    
    await message.answer(
        f"✅ *Оплата прошла успешно!*\n\n"
        f"⭐ Премиум активирован для Discord ID `{discord_id}` на 30 дней!\n"
        f"💰 Оплачено: {total_amount} Stars",
        parse_mode="Markdown"
    )
    
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, f"🎉 Новая покупка!\n👤 {user_name}\n🆔 Discord ID: {discord_id}\n💰 {total_amount} Stars")
        except:
            pass

@dp.message(Command("help"))
async def help_command(message: types.Message):
    await message.answer(
        "📚 *Доступные команды:*\n\n"
        "/start — Главное менú\n"
        "/link — Привязать Discord ID\n"
        "/balance — Баланс Stars (админ)\n"
        "/help — Помощь",
        parse_mode="Markdown"
    )

async def main():
    logging.basicConfig(level=logging.INFO)
    print("🚀 Telegram бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
