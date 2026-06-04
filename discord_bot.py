import discord
from discord.ext import commands
from discord import app_commands
import re
import os
from datetime import datetime, timedelta
from difflib import get_close_matches
from threading import Thread
from flask import Flask
import google.generativeai as genai
import sqlite3

# ===== ВЕБ-СЕРВЕР ДЛЯ RENDER =====
app = Flask(__name__)

@app.route('/')
def health_check():
    return "✅ Discord bot is alive!", 200

def run_web_server():
    app.run(host='0.0.0.0', port=8080)

# ===== НАСТРОЙКИ =====
TOKEN = os.environ.get("DISCORD_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if not TOKEN:
    print("❌ DISCORD_TOKEN не найден!")
    exit(1)
if not GEMINI_API_KEY:
    print("❌ GEMINI_API_KEY не найден!")
    exit(1)

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-2.0-flash')

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
    c.execute('''
        CREATE TABLE IF NOT EXISTS premium_users (
            discord_id TEXT PRIMARY KEY,
            telegram_id TEXT,
            expires_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

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
    c.execute('''
        INSERT INTO premium_users (discord_id, telegram_id, expires_at)
        VALUES (?, ?, ?)
        ON CONFLICT(discord_id) DO UPDATE SET
            expires_at = datetime(expires_at, '+' || ? || ' days'),
            telegram_id = COALESCE(?, telegram_id)
    ''', (discord_id, telegram_id, expires_at, days, telegram_id))
    conn.commit()
    conn.close()

init_db()

# ========== ПОЛНЫЙ УК ==========
uk_sections = {
    "VI": "Преступления против жизни и здоровья",
    "VII": "Преступления против свободы, чести и достоинства",
    "VIII": "Преступления против половой неприкосновенности",
    "X": "Преступления против собственности",
    "XI": "Преступления в сфере экономической деятельности",
    "XII": "Преступления против общественной безопасности",
    "XIII": "Преступления в сфере оборота наркотиков",
    "XV": "Преступления против власти",
    "XVI": "Преступления против правосудия",
    "XVII": "Преступления против управления",
    "XIX": "Преступления против окружающей среды",
}

uk_laws = [
    {"article": "6.1", "section": "VI", "title": "Умышленное нанесение побоев", "penalty": "от 1 до 3 лет", "stars": "★★★", "note": ""},
    {"article": "6.2", "section": "VI", "title": "Убийство", "penalty": "от 2 до 4 лет", "stars": "★★★★", "note": ""},
    {"article": "6.3", "section": "VI", "title": "Тяжкое убийство", "penalty": "от 4 до 5 лет", "stars": "★★★★★", "note": ""},
    {"article": "6.4", "section": "VI", "title": "Угроза убийством", "penalty": "от 2 до 3 лет, либо штраф $30.000-$50.000", "stars": "★★★", "note": ""},
    {"article": "7.1", "section": "VII", "title": "Похищение человека", "penalty": "от 4 до 5 лет", "stars": "★★★★★", "note": ""},
    {"article": "7.4", "section": "VII", "title": "Клевета", "penalty": "от 2 до 3 лет, либо штраф $40.000-$80.000", "stars": "★★★", "note": ""},
    {"article": "8.1", "section": "VIII", "title": "Изнасилование", "penalty": "от 3 до 4 лет", "stars": "★★★★", "note": ""},
    {"article": "10.1", "section": "X", "title": "Кража", "penalty": "от 2 до 3 лет", "stars": "★★★", "note": ""},
    {"article": "10.2", "section": "X", "title": "Мошенничество", "penalty": "от 2 до 3 лет", "stars": "★★★", "note": ""},
    {"article": "10.3", "section": "X", "title": "Грабеж", "penalty": "от 2 до 3 лет", "stars": "★★★", "note": ""},
    {"article": "10.4", "section": "X", "title": "Разбой", "penalty": "от 2 до 4 лет", "stars": "★★★★", "note": ""},
    {"article": "10.5", "section": "X", "title": "Угон авто", "penalty": "от 1 до 3 лет", "stars": "★★★", "note": ""},
    {"article": "10.9", "section": "X", "title": "Проникновение в жилище", "penalty": "от 3 до 4 лет", "stars": "★★★★", "note": ""},
    {"article": "11.3", "section": "XI", "title": "Уклонение от налогов", "penalty": "взыскание ×2 + от 3 до 5 лет", "stars": "★★★★★", "note": ""},
    {"article": "12.1", "section": "XII", "title": "Терроризм", "penalty": "от 4 до 5 лет", "stars": "★★★★★", "note": ""},
    {"article": "12.8", "section": "XII", "title": "Хранение оружия", "penalty": "от 3 до 4 лет, либо штраф $20.000-$60.000", "stars": "★★★★", "note": ""},
    {"article": "12.14", "section": "XII", "title": "Хулиганство", "penalty": "до 2 лет, либо штраф $30.000-$40.000", "stars": "★★", "note": ""},
    {"article": "13.2", "section": "XIII", "title": "Сбыт наркотиков", "penalty": "от 3 до 5 лет", "stars": "★★★★★", "note": ""},
    {"article": "13.3", "section": "XIII", "title": "Хранение наркотиков", "penalty": "от 2 до 4 лет", "stars": "★★★★", "note": ""},
    {"article": "15.4", "section": "XV", "title": "Получение взятки", "penalty": "от 4 до 5 лет", "stars": "★★★★★", "note": ""},
    {"article": "15.5", "section": "XV", "title": "Дача взятки", "penalty": "от 4 до 5 лет", "stars": "★★★★★", "note": ""},
    {"article": "16.15", "section": "XVI", "title": "Побег из тюрьмы", "penalty": "от 1 до 5 лет", "stars": "★..★★★★★", "note": ""},
    {"article": "17.1", "section": "XVII", "title": "Посягательство на жизнь полицейского", "penalty": "от 4 до 5 лет", "stars": "★★★★★", "note": ""},
    {"article": "17.3", "section": "XVII", "title": "Оскорбление полицейского", "penalty": "от 1 до 3 лет, либо штраф $20.000-$50.000", "stars": "★★★", "note": ""},
    {"article": "19.1", "section": "XIX", "title": "Браконьерство", "penalty": "от 1 до 3 лет", "stars": "★★★", "note": ""},
]

# ========== БАЗА ПК ==========
pk_laws = [
    {"article": "15", "title": "Срок задержания", "penalty": "Максимум 1 час", "stars": "⏰", "note": ""},
    {"article": "16", "title": "Основания задержания", "penalty": "8 оснований", "stars": "🔍", "note": ""},
    {"article": "17", "title": "Порядок задержания", "penalty": "11 шагов", "stars": "📋", "note": ""},
    {"article": "19", "title": "Задержание госслужащего", "penalty": "Уведомить руководство и прокуратуру", "stars": "👮", "note": ""},
    {"article": "20", "title": "Освобождение подозреваемого", "penalty": "7 оснований", "stars": "🔓", "note": ""},
    {"article": "22", "title": "Права задержанного", "penalty": "5 прав", "stars": "📜", "note": ""},
    {"article": "28", "title": "Личный обыск", "penalty": "Только при задержании", "stars": "🔎", "note": ""},
    {"article": "29", "title": "Обыск транспорта", "penalty": "Обыск с ордером", "stars": "🚗", "note": ""},
    {"article": "31", "title": "Видеофиксация", "penalty": "Обязательная запись", "stars": "🎥", "note": ""},
    {"article": "33", "title": "Залог", "penalty": "от $25.000 + $25.000 за звезду", "stars": "💰", "note": ""},
    {"article": "36", "title": "Применение силы", "penalty": "5 стадий", "stars": "💪", "note": ""},
    {"article": "9", "title": "Обжалование", "penalty": "48 часов", "stars": "📋", "note": ""},
    {"article": "12", "title": "Недопустимые доказательства", "penalty": "Показания до прав", "stars": "🚫", "note": ""},
    {"article": "56", "title": "Адвокат на допросе", "penalty": "Присутствует", "stars": "👨‍⚖️", "note": ""},
    {"article": "М7", "title": "Правило Миранды", "penalty": "Право молчать", "stars": "📢", "note": ""},
]

# ========== ФУНКЦИЯ ДЛЯ ИИ ==========
async def ask_ai(question: str) -> str:
    try:
        uk_context = "\n".join([f"Ст.{l['article']}: {l['title']}" for l in uk_laws[:20]])
        pk_context = "\n".join([f"Ст.{p['article']}: {p['title']}" for p in pk_laws[:10]])
        prompt = f"""Ты — юридический помощник в игре Majestic RP. Отвечай на вопросы по УК и ПК штата Сан-Андреас.
Кратко (2-4 предложения), по делу, ссылайся на статьи.

УК: {uk_context}
ПК: {pk_context}

Вопрос: {question}"""
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"❌ Ошибка ИИ: {str(e)}"

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
        if (law["title"].lower() in query_lower or query_lower in law["title"].lower() or
            law["penalty"].lower() in query_lower or query_lower in law["penalty"].lower()):
            found.append(law)
    
    if not found:
        all_texts = []
        for law in database:
            all_texts.append(law["title"].lower())
            all_texts.append(law["penalty"].lower())
        matches = get_close_matches(query_lower, all_texts, n=3, cutoff=0.5)
        for match in matches:
            for law in database:
                if match == law["title"].lower() or match == law["penalty"].lower():
                    if law not in found:
                        found.append(law)
    return found

# ========== ПРЕФИКСНЫЕ КОМАНДЫ (работают всегда) ==========
@bot.command(name="ук")
async def uk_prefix(ctx, *, query: str):
    """!ук убийство"""
    results = smart_search(query, uk_laws)
    if not results:
        await ctx.send(f"❌ Ничего не найдено по `{query}`")
        return
    if len(results) > 1:
        await ctx.send(f"🔍 Найдено {len(results)} статей: {', '.join([r['article'] for r in results[:5]])}")
        return
    law = results[0]
    section_name = uk_sections.get(law["section"], "Общая часть")
    embed = discord.Embed(title=f"⚖️ Ст {law['article']} УК", description=f"**{law['title']}**\n📌 {section_name}\n{law['stars']}", color=discord.Color.red())
    embed.add_field(name="📝 Наказание", value=law['penalty'], inline=False)
    await ctx.send(embed=embed)

@bot.command(name="пк")
async def pk_prefix(ctx, *, query: str):
    """!пк задержание"""
    results = smart_search(query, pk_laws)
    if not results:
        await ctx.send(f"❌ Ничего не найдено по `{query}`")
        return
    if len(results) > 1:
        await ctx.send(f"🔍 Найдено {len(results)} статей")
        return
    law = results[0]
    embed = discord.Embed(title=f"📜 Ст {law['article']} ПК", description=f"**{law['title']}**\n{law['stars']}", color=discord.Color.green())
    embed.add_field(name="📝 Содержание", value=law['penalty'], inline=False)
    await ctx.send(embed=embed)

@bot.command(name="вопрос")
async def ask_prefix(ctx, *, question: str):
    """!вопрос Какое наказание за кражу?"""
    async with ctx.typing():
        answer = await ask_ai(question)
        embed = discord.Embed(title="🤖 ИИ-адвокат", description=answer, color=discord.Color.blue())
        await ctx.send(embed=embed)

@bot.command(name="статус")
async def status_prefix(ctx):
    """!статус — проверить подписку"""
    user_id = str(ctx.author.id)
    if is_premium(user_id):
        expiry = get_premium_expiry(user_id)
        await ctx.send(f"✅ Премиум активен до {expiry}")
    else:
        await ctx.send("❌ Премиум не активен. Купить: @LawyerPayBot")

# ========== СЛЭШ-КОМАНДЫ ==========
@bot.tree.command(name="ук", description="Поиск по Уголовному кодексу")
@app_commands.describe(query="Номер статьи или название")
async def uk_cmd(interaction: discord.Interaction, query: str):
    await interaction.response.defer()
    results = smart_search(query, uk_laws)
    if not results:
        await interaction.followup.send(f"❌ Ничего не найдено по `{query}`")
        return
    if len(results) > 1:
        embed = discord.Embed(title=f"🔍 Найдено {len(results)} статей", color=discord.Color.orange())
        for law in results[:5]:
            section_name = uk_sections.get(law["section"], "Общая часть")
            embed.add_field(name=f"Ст.{law['article']} {law['stars']}", value=f"{law['title']}\n{section_name}", inline=False)
        await interaction.followup.send(embed=embed)
        return
    law = results[0]
    section_name = uk_sections.get(law["section"], "Общая часть")
    embed = discord.Embed(title=f"⚖️ Ст {law['article']} УК", description=f"**{law['title']}**\n📌 {section_name}\n{law['stars']}", color=discord.Color.red())
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
    if len(results) > 1:
        embed = discord.Embed(title=f"🔍 Найдено {len(results)} статей", color=discord.Color.green())
        for law in results[:5]:
            embed.add_field(name=f"Ст.{law['article']} {law['stars']}", value=f"{law['title']}", inline=False)
        await interaction.followup.send(embed=embed)
        return
    law = results[0]
    embed = discord.Embed(title=f"📜 Ст {law['article']} ПК", description=f"**{law['title']}**\n{law['stars']}", color=discord.Color.green())
    embed.add_field(name="📝 Содержание", value=law['penalty'], inline=False)
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="вопрос", description="Задать вопрос ИИ-адвокату")
@app_commands.describe(question="Ваш вопрос")
async def ask_cmd(interaction: discord.Interaction, question: str):
    await interaction.response.defer()
    answer = await ask_ai(question)
    embed = discord.Embed(title="⚖️ ИИ-адвокат", description=answer, color=discord.Color.purple())
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="статус", description="Проверить статус подписки")
async def status_cmd(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    if is_premium(user_id):
        expiry = get_premium_expiry(user_id)
        embed = discord.Embed(title="💎 Статус подписки", description=f"✅ Премиум активен до {expiry}", color=discord.Color.green())
    else:
        embed = discord.Embed(title="💎 Статус подписки", description="❌ Премиум не активен\nКупить: @LawyerPayBot", color=discord.Color.orange())
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="справка", description="Все команды")
async def help_cmd(interaction: discord.Interaction):
    embed = discord.Embed(title="📚 Помощь", color=discord.Color.gold())
    embed.add_field(name="⚖️ УК", value="`/ук убийство` или `!ук убийство`", inline=False)
    embed.add_field(name="📜 ПК", value="`/пк задержание` или `!пк задержание`", inline=False)
    embed.add_field(name="🤖 ИИ", value="`/вопрос` или `!вопрос`", inline=False)
    embed.add_field(name="💎 Подписка", value="`/статус` или `!статус`", inline=False)
    await interaction.response.send_message(embed=embed)

# ========== СОБЫТИЕ ЗАПУСКА С СИНХРОНИЗАЦИЕЙ ==========
@bot.event
async def on_ready():
    print(f"✅ Discord бот {bot.user} готов!")
    print(f"📜 УК: {len(uk_laws)} статей | ПК: {len(pk_laws)} статей")
    
    # ПРИНУДИТЕЛЬНАЯ СИНХРОНИЗАЦИЯ СЛЭШ-КОМАНД
    try:
        synced = await bot.tree.sync()
        print(f"🔗 Синхронизировано {len(synced)} слэш-команд")
    except Exception as e:
        print(f"❌ Ошибка синхронизации: {e}")
    
    Thread(target=run_web_server, daemon=True).start()
    print("🌐 Веб-сервер запущен")

# ЗАПУСК
bot.run(TOKEN)
