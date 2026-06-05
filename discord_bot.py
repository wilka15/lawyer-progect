import discord
from discord.ext import commands
from discord import app_commands
import re
import os
from datetime import datetime, timedelta
from difflib import get_close_matches
from threading import Thread
from flask import Flask, jsonify
import sqlite3

# ===== ВЕБ-СЕРВЕР =====
app = Flask(__name__)

@app.route('/')
def health_check():
    return "✅ Discord bot is alive!", 200

@app.route('/api/stats')
def api_stats():
    """API для сайта — возвращает статистику в формате JSON"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute('SELECT COUNT(*) FROM premium_users')
    total_users = c.fetchone()[0]
    
    now = datetime.now().isoformat()
    c.execute('SELECT COUNT(*) FROM premium_users WHERE expires_at > ?', (now,))
    active_premium = c.fetchone()[0]
    
    current_month = datetime.now().strftime("%Y-%m")
    c.execute('SELECT SUM(count) FROM request_counts WHERE month = ?', (current_month,))
    total_requests_row = c.fetchone()
    total_requests = total_requests_row[0] if total_requests_row[0] else 0
    
    conn.close()
    
    return jsonify({
        "total_users": total_users,
        "active_premium": active_premium,
        "total_requests": total_requests,
        "month": current_month,
        "uk_articles": len(uk_laws),
        "pk_articles": len(pk_laws),
        "status": "online",
        "uptime": "24/7"
    })

def run_web_server():
    app.run(host='0.0.0.0', port=8080)

# ===== НАСТРОЙКИ =====
TOKEN = os.environ.get("DISCORD_TOKEN")
if not TOKEN:
    print("❌ DISCORD_TOKEN не найден!")
    exit(1)

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

OWNER_ID = int(os.environ.get("OWNER_ID", "920268444983775252"))

def is_owner(interaction: discord.Interaction) -> bool:
    return interaction.user.id == OWNER_ID

# ========== БАЗА ДАННЫХ ==========
DB_PATH = "premium.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS premium_users (discord_id TEXT PRIMARY KEY, telegram_id TEXT, expires_at TIMESTAMP, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
    c.execute('CREATE TABLE IF NOT EXISTS referrals (discord_id TEXT PRIMARY KEY, invited_by TEXT, invited_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
    c.execute('CREATE TABLE IF NOT EXISTS request_counts (discord_id TEXT PRIMARY KEY, month TEXT, count INTEGER DEFAULT 0, bonus_requests INTEGER DEFAULT 0)')
    conn.commit()
    conn.close()
    print("✅ База данных инициализирована")

init_db()

# ========== ФУНКЦИИ ==========
def is_premium(discord_id: str) -> bool:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT expires_at FROM premium_users WHERE discord_id = ?', (discord_id,))
    row = c.fetchone()
    conn.close()
    if row and row[0]:
        return datetime.fromisoformat(row[0]) > datetime.now()
    return False

def get_premium_expiry(discord_id: str) -> str:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT expires_at FROM premium_users WHERE discord_id = ?', (discord_id,))
    row = c.fetchone()
    conn.close()
    return row[0][:10] if row and row[0] else None

def set_premium(discord_id: str, days: int, telegram_id: str = None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    expires_at = (datetime.now() + timedelta(days=days)).isoformat()
    c.execute('INSERT INTO premium_users (discord_id, telegram_id, expires_at) VALUES (?, ?, ?) ON CONFLICT(discord_id) DO UPDATE SET expires_at = datetime(expires_at, "+" || ? || " days"), telegram_id = COALESCE(?, telegram_id)', (discord_id, telegram_id, expires_at, days, telegram_id))
    conn.commit()
    conn.close()

def get_all_premium_users() -> list:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT discord_id, expires_at FROM premium_users WHERE expires_at > ?', (datetime.now().isoformat(),))
    rows = c.fetchall()
    conn.close()
    return rows

def get_invited_by(discord_id: str) -> str:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT invited_by FROM referrals WHERE discord_id = ?', (discord_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None

def add_referral(invited_id: str, inviter_id: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('INSERT INTO referrals (discord_id, invited_by) VALUES (?, ?) ON CONFLICT(discord_id) DO NOTHING', (invited_id, inviter_id))
    conn.commit()
    conn.close()
    set_premium(inviter_id, 14)
    add_bonus_requests(invited_id, 5)

def get_referral_count(discord_id: str) -> int:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM referrals WHERE invited_by = ?', (discord_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else 0

def get_user_requests(discord_id: str) -> tuple:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    current_month = datetime.now().strftime("%Y-%m")
    c.execute('SELECT count, bonus_requests FROM request_counts WHERE discord_id = ? AND month = ?', (discord_id, current_month))
    row = c.fetchone()
    conn.close()
    return row if row else (0, 0)

def increment_requests(discord_id: str) -> int:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    current_month = datetime.now().strftime("%Y-%m")
    c.execute('INSERT INTO request_counts (discord_id, month, count, bonus_requests) VALUES (?, ?, 1, 0) ON CONFLICT(discord_id) DO UPDATE SET count = count + 1', (discord_id, current_month))
    conn.commit()
    conn.close()
    return get_user_requests(discord_id)[0]

def add_bonus_requests(discord_id: str, amount: int):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    current_month = datetime.now().strftime("%Y-%m")
    c.execute('INSERT INTO request_counts (discord_id, month, count, bonus_requests) VALUES (?, ?, 0, ?) ON CONFLICT(discord_id) DO UPDATE SET bonus_requests = bonus_requests + ?', (discord_id, current_month, amount, amount))
    conn.commit()
    conn.close()

def get_remaining_free_requests(discord_id: str) -> int:
    if is_premium(discord_id):
        return 999
    used, bonus = get_user_requests(discord_id)
    return max(0, (5 + bonus) - used)

def check_and_increment(discord_id: str) -> tuple:
    if is_premium(discord_id):
        return True, 999, 0
    remaining = get_remaining_free_requests(discord_id)
    if remaining <= 0:
        used, bonus = get_user_requests(discord_id)
        return False, 0, used
    used, bonus = get_user_requests(discord_id)
    increment_requests(discord_id)
    return True, remaining - 1, used + 1

# ========== УК (сокращённый для примера, добавьте свои статьи) ==========
uk_laws = [
    {"article": "6.1", "title": "Умышленное нанесение побоев", "penalty": "от 1 до 3 лет", "stars": "★★★", "note": ""},
    {"article": "6.2", "title": "Убийство", "penalty": "от 2 до 4 лет", "stars": "★★★★", "note": ""},
    {"article": "10.1", "title": "Кража", "penalty": "от 2 до 3 лет", "stars": "★★★", "note": ""},
]

# ========== ПК (сокращённый для примера) ==========
pk_laws = [
    {"article": "17", "title": "Порядок задержания", "penalty": "11 шагов", "stars": "📋", "note": ""},
    {"article": "22", "title": "Права задержанного", "penalty": "Адвокат, молчание, звонок", "stars": "📜", "note": ""},
]

# ========== ПОИСК ==========
def smart_search(query: str, database: list):
    query_lower = query.lower().strip()
    found = []
    match_num = re.search(r'(\d{1,2}(?:\.\d{1,2})?)', query_lower)
    if match_num:
        art_num = match_num.group(1)
        for law in database:
            if law["article"] == art_num:
                return [law]
    for law in database:
        if law["title"].lower() in query_lower or query_lower in law["title"].lower():
            found.append(law)
    return found

# ========== КОМАНДЫ ==========
@bot.tree.command(name="ук", description="Поиск по Уголовному кодексу")
@app_commands.describe(query="Номер статьи или название")
async def uk_cmd(interaction: discord.Interaction, query: str):
    await interaction.response.defer()
    results = smart_search(query, uk_laws)
    if not results:
        await interaction.followup.send(f"❌ Ничего не найдено по `{query}`")
        return
    law = results[0]
    embed = discord.Embed(title=f"⚖️ Ст {law['article']} УК", description=law['title'], color=discord.Color.red())
    embed.add_field(name="📝 Наказание", value=law['penalty'], inline=False)
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="пк", description="Поиск по Процессуальному кодексу")
@app_commands.describe(query="Номер статьи или тема")
async def pk_cmd(interaction: discord.Interaction, query: str):
    await interaction.response.defer()
    results = smart_search(query, pk_laws)
    if not results:
        await interaction.followup.send(f"❌ Ничего не найдено по `{query}`")
        return
    law = results[0]
    embed = discord.Embed(title=f"📜 Ст {law['article']} ПК", description=law['title'], color=discord.Color.green())
    embed.add_field(name="📝 Содержание", value=law['penalty'], inline=False)
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="статус", description="Проверить статус подписки")
async def status_cmd(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    if is_premium(user_id):
        expiry = get_premium_expiry(user_id)
        embed = discord.Embed(title="💎 Статус", description=f"✅ Премиум активен до {expiry}", color=discord.Color.green())
    else:
        embed = discord.Embed(title="💎 Статус", description="❌ Премиум не активен\nКупить: @lawyer_pay_bot", color=discord.Color.orange())
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="справка", description="Все команды")
async def help_cmd(interaction: discord.Interaction):
    embed = discord.Embed(title="📚 Помощь", color=discord.Color.gold())
    embed.add_field(name="⚖️ УК", value="`/ук убийство`", inline=False)
    embed.add_field(name="📜 ПК", value="`/пк задержание`", inline=False)
    embed.add_field(name="💎 Премиум", value="`/статус`", inline=False)
    await interaction.response.send_message(embed=embed)

@bot.event
async def on_ready():
    print(f"✅ Discord бот {bot.user} готов!")
    print(f"📜 УК: {len(uk_laws)} статей | ПК: {len(pk_laws)} статей")
    try:
        synced = await bot.tree.sync()
        print(f"🔗 Синхронизировано {len(synced)} слэш-команд")
    except Exception as e:
        print(f"❌ Ошибка синхронизации: {e}")
    Thread(target=run_web_server, daemon=True).start()
    print("🌐 Веб-сервер запущен")

bot.run(TOKEN)
