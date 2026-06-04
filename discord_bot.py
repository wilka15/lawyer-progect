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
import database as db

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

# ========== ПОЛНЫЙ УК (ВСЕ СТАТЬИ) ==========
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
    # Глава VI
    {"article": "6.1", "section": "VI", "title": "Умышленное нанесение побоев", "penalty": "от 1 до 3 лет", "stars": "★★★", "note": ""},
    {"article": "6.2", "section": "VI", "title": "Убийство", "penalty": "от 2 до 4 лет", "stars": "★★★★", "note": ""},
    {"article": "6.3", "section": "VI", "title": "Тяжкое убийство", "penalty": "от 4 до 5 лет", "stars": "★★★★★", "note": ""},
    {"article": "6.4", "section": "VI", "title": "Угроза убийством", "penalty": "от 2 до 3 лет, либо штраф $30.000-$50.000", "stars": "★★★", "note": ""},
    {"article": "6.5", "section": "VI", "title": "Воспрепятствование деятельности медработника", "penalty": "от 2 до 3 лет, либо штраф $5.000-$20.000", "stars": "★★★", "note": ""},
    # Глава VII
    {"article": "7.1", "section": "VII", "title": "Похищение человека", "penalty": "от 4 до 5 лет", "stars": "★★★★★", "note": ""},
    {"article": "7.1.1", "section": "VII", "title": "Незаконное лишение свободы", "penalty": "от 3 до 4 лет", "stars": "★★★★", "note": ""},
    {"article": "7.2", "section": "VII", "title": "Использование рабского труда", "penalty": "от 3 до 4 лет", "stars": "★★★★", "note": ""},
    {"article": "7.3", "section": "VII", "title": "Купля-продажа человека", "penalty": "от 3 до 4 лет", "stars": "★★★★", "note": ""},
    {"article": "7.4", "section": "VII", "title": "Клевета", "penalty": "от 2 до 3 лет, либо штраф $40.000-$80.000", "stars": "★★★", "note": ""},
    {"article": "7.4.1", "section": "VII", "title": "Клевета с обвинением в преступлении", "penalty": "от 2 до 3 лет, либо штраф $40.000-$80.000", "stars": "★★★", "note": ""},
    # Глава VIII
    {"article": "8.1", "section": "VIII", "title": "Изнасилование", "penalty": "от 3 до 4 лет", "stars": "★★★★", "note": ""},
    {"article": "8.2", "section": "VIII", "title": "Понуждение к половому акту", "penalty": "от 2 до 3 лет", "stars": "★★★", "note": ""},
    {"article": "8.3", "section": "VIII", "title": "Сексуальное домогательство", "penalty": "от 2 до 3 лет", "stars": "★★★", "note": ""},
    # Глава X
    {"article": "10.1", "section": "X", "title": "Кража", "penalty": "от 2 до 3 лет", "stars": "★★★", "note": ""},
    {"article": "10.2", "section": "X", "title": "Мошенничество", "penalty": "от 2 до 3 лет", "stars": "★★★", "note": ""},
    {"article": "10.2.1", "section": "X", "title": "Вымогательство", "penalty": "от 2 до 3 лет", "stars": "★★★", "note": ""},
    {"article": "10.3", "section": "X", "title": "Грабеж", "penalty": "от 2 до 3 лет", "stars": "★★★", "note": ""},
    {"article": "10.4", "section": "X", "title": "Разбой", "penalty": "от 2 до 4 лет", "stars": "★★★★", "note": ""},
    {"article": "10.5", "section": "X", "title": "Угон авто", "penalty": "от 1 до 3 лет", "stars": "★★★", "note": ""},
    {"article": "10.5.1", "section": "X", "title": "Угон гос. транспорта", "penalty": "от 3 до 4 лет", "stars": "★★★★", "note": ""},
    {"article": "10.6", "section": "X", "title": "Уничтожение чужого имущества", "penalty": "от 1 до 3 лет, либо штраф $20.000-$60.000", "stars": "★★★", "note": ""},
    {"article": "10.9", "section": "X", "title": "Проникновение в жилище", "penalty": "от 3 до 4 лет", "stars": "★★★★", "note": ""},
    # Глава XI
    {"article": "11.1", "section": "XI", "title": "Предпринимательство без регистрации", "penalty": "от 1 до 3 лет, либо штраф $50.000-$100.000", "stars": "★★★", "note": ""},
    {"article": "11.3", "section": "XI", "title": "Уклонение от налогов", "penalty": "взыскание ×2 + от 3 до 5 лет", "stars": "★★★★★", "note": ""},
    {"article": "11.6", "section": "XI", "title": "Финансовые махинации", "penalty": "от 4 до 5 лет", "stars": "★★★★★", "note": ""},
    # Глава XII
    {"article": "12.1", "section": "XII", "title": "Терроризм", "penalty": "от 4 до 5 лет", "stars": "★★★★★", "note": ""},
    {"article": "12.8", "section": "XII", "title": "Незаконное хранение оружия", "penalty": "от 3 до 4 лет, либо штраф $20.000-$60.000", "stars": "★★★★", "note": ""},
    {"article": "12.8.1", "section": "XII", "title": "Оружие гособразца у гражданских", "penalty": "от 3 до 5 лет", "stars": "★★★★★", "note": ""},
    {"article": "12.14", "section": "XII", "title": "Хулиганство", "penalty": "до 2 лет, либо штраф $30.000-$40.000", "stars": "★★", "note": ""},
    # Глава XIII
    {"article": "13.1", "section": "XIII", "title": "Кустарное производство наркотиков", "penalty": "от 2 до 4 лет", "stars": "★★★★", "note": ""},
    {"article": "13.2", "section": "XIII", "title": "Сбыт наркотиков", "penalty": "от 3 до 5 лет", "stars": "★★★★★", "note": ""},
    {"article": "13.3", "section": "XIII", "title": "Хранение наркотиков от 5 грамм", "penalty": "от 2 до 4 лет", "stars": "★★★★", "note": ""},
    {"article": "13.4", "section": "XIII", "title": "Хранение наркотиков от 20 грамм", "penalty": "от 4 до 5 лет", "stars": "★★★★★", "note": ""},
    # Глава XV
    {"article": "15.4", "section": "XV", "title": "Получение взятки", "penalty": "от 4 до 5 лет", "stars": "★★★★★", "note": ""},
    {"article": "15.5", "section": "XV", "title": "Дача взятки", "penalty": "от 4 до 5 лет", "stars": "★★★★★", "note": ""},
    {"article": "15.6", "section": "XV", "title": "Халатность", "penalty": "от 2 до 5 лет, либо штраф $40.000-$70.000", "stars": "★★★★★", "note": ""},
    {"article": "15.7", "section": "XV", "title": "Деструктивное поведение госслужащего", "penalty": "от 1 до 3 лет, либо штраф $30.000-$70.000", "stars": "★★★", "note": ""},
    # Глава XVI
    {"article": "16.1", "section": "XVI", "title": "Вмешательство в деятельность суда", "penalty": "от 3 до 4 лет", "stars": "★★★★", "note": ""},
    {"article": "16.2", "section": "XVI", "title": "Угроза судье или прокурору", "penalty": "от 4 до 5 лет", "stars": "★★★★★", "note": ""},
    {"article": "16.3", "section": "XVI", "title": "Привлечение невиновного", "penalty": "от 3 до 5 лет", "stars": "★★★★★", "note": ""},
    {"article": "16.4", "section": "XVI", "title": "Незаконное задержание", "penalty": "от 3 до 5 лет", "stars": "★★★★★", "note": ""},
    {"article": "16.8", "section": "XVI", "title": "Ложные показания в суде", "penalty": "от 3 до 4 лет", "stars": "★★★★", "note": ""},
    {"article": "16.15", "section": "XVI", "title": "Побег из тюрьмы", "penalty": "от 1 до 5 лет", "stars": "★..★★★★★", "note": ""},
    {"article": "16.16", "section": "XVI", "title": "Ложный донос", "penalty": "от 2 до 4 лет, либо штраф $40.000-$80.000", "stars": "★★★★", "note": ""},
    # Глава XVII
    {"article": "17.1", "section": "XVII", "title": "Посягательство на жизнь полицейского", "penalty": "от 4 до 5 лет", "stars": "★★★★★", "note": ""},
    {"article": "17.2", "section": "XVII", "title": "Насилие в отношении полицейского", "penalty": "от 3 до 4 лет", "stars": "★★★★", "note": ""},
    {"article": "17.3", "section": "XVII", "title": "Оскорбление полицейского", "penalty": "от 1 до 3 лет, либо штраф $20.000-$50.000", "stars": "★★★", "note": ""},
    {"article": "17.6", "section": "XVII", "title": "Неповиновение законному требованию", "penalty": "от 2 до 3 лет, либо штраф $20.000-$60.000", "stars": "★★★", "note": ""},
    {"article": "17.7", "section": "XVII", "title": "Отказ от оплаты штрафа", "penalty": "от 2 до 3 лет, либо штраф $20.000-$60.000", "stars": "★★★", "note": ""},
    {"article": "17.8", "section": "XVII", "title": "Подделка удостоверения", "penalty": "от 3 до 4 лет", "stars": "★★★★", "note": ""},
    {"article": "17.9", "section": "XVII", "title": "Оскорбление человека в общественном месте", "penalty": "до 2 лет", "stars": "★★", "note": ""},
    # Глава XIX
    {"article": "19.1", "section": "XIX", "title": "Браконьерство", "penalty": "от 1 до 3 лет", "stars": "★★★", "note": ""},
    {"article": "19.2", "section": "XIX", "title": "Жестокое обращение с животным", "penalty": "от 2 до 4 лет, либо штраф $30.000-$80.000", "stars": "★★★", "note": ""},
]

# ========== БАЗА ПК ==========
pk_laws = [
    {"article": "15", "title": "Срок задержания", "penalty": "Максимум 1 час", "stars": "⏰", "note": ""},
    {"article": "16", "title": "Основания задержания", "penalty": "8 оснований: на месте, следы, 3 свидетеля, фото/видео, ордер, требование прокурора, ориентировка, боло-розыск", "stars": "🔍", "note": ""},
    {"article": "17", "title": "Порядок задержания", "penalty": "Наручники → представиться → Миранда → обыск → объяснить причину → доставить в участок → проверить документы → фоторобот → допрос → предложить права → реализовать права", "stars": "📋", "note": ""},
    {"article": "19", "title": "Задержание госслужащего", "penalty": "Уведомить руководство и прокуратуру. Если прокурор не приехал за 20 минут — освободить", "stars": "👮", "note": ""},
    {"article": "20", "title": "Освобождение подозреваемого", "penalty": "Не подтвердилось, нет лишения свободы, нарушен порядок, прошёл час, неприкосновенность, неуполномоченный сотрудник, незаконные доказательства", "stars": "🔓", "note": ""},
    {"article": "22", "title": "Права задержанного", "penalty": "Адвокат, молчание, ходатайства, встреча с адвокатом (10 мин), звонок (3 мин)", "stars": "📜", "note": ""},
    {"article": "28", "title": "Личный обыск", "penalty": "Только при задержании или аресте. Первичный — оружие/наркотики. Вторичный — всё изымается", "stars": "🔎", "note": ""},
    {"article": "29", "title": "Обыск транспорта", "penalty": "Обыск только с ордером CS. Осмотр — при ориентировке или подозрении", "stars": "🚗", "note": ""},
    {"article": "31", "title": "Видеофиксация", "penalty": "Обязательная запись, хранение 48 часов", "stars": "🎥", "note": ""},
    {"article": "33", "title": "Залог", "penalty": "от $25.000 + $25.000 за звезду", "stars": "💰", "note": ""},
    {"article": "36", "title": "Применение силы", "penalty": "1. Присутствие, 2. Приказ, 3. Физ. сила, 4. Спецсредства, 5. Огнестрельное оружие", "stars": "💪", "note": ""},
    {"article": "9", "title": "Обжалование", "penalty": "48 часов. Жалоба руководителю, в прокуратуру или суд", "stars": "📋", "note": ""},
    {"article": "12", "title": "Недопустимые доказательства", "penalty": "Показания до прав, слухи, улики добытые незаконно", "stars": "🚫", "note": ""},
    {"article": "56", "title": "Адвокат на допросе", "penalty": "Присутствует, может взять 5-минутный перерыв, вправе заявлять о нарушениях", "stars": "👨‍⚖️", "note": ""},
    {"article": "М7", "title": "Правило Миранды", "penalty": "«Вы имеете право хранить молчание. Всё, что скажете, может быть использовано против вас. Вы имеете право на адвоката»", "stars": "📢", "note": ""},
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

# ========== СОБЫТИЕ ==========
@bot.event
async def on_ready():
    print(f"✅ Discord бот {bot.user} готов!")
    print(f"📜 УК: {len(uk_laws)} статей | ПК: {len(pk_laws)} статей")
    Thread(target=run_web_server, daemon=True).start()
    print("🌐 Веб-сервер запущен")

# ========== КОМАНДЫ ==========

@bot.tree.command(name="status", description="Проверить статус подписки")
async def status_cmd(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    
    if db.is_premium(user_id):
        expiry = db.get_premium_expiry(user_id)
        embed = discord.Embed(title="💎 Статус подписки", description=f"✅ Премиум **активен**\n📅 Действует до: {expiry}", color=discord.Color.green())
    else:
        embed = discord.Embed(title="💎 Статус подписки", description="❌ Премиум **не активен**\n\nКупить: @LawyerPayBot", color=discord.Color.orange())
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="give", description="[АДМИН] Выдать премиум")
@app_commands.describe(user="Пользователь", days="Количество дней")
async def give_cmd(interaction: discord.Interaction, user: discord.User, days: int = 30):
    if not is_owner(interaction):
        await interaction.response.send_message("❌ Нет прав!", ephemeral=True)
        return
    db.set_premium(str(user.id), days)
    await interaction.response.send_message(f"✅ {user.mention} получил премиум на {days} дней!")

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
    if law['note']:
        embed.add_field(name="📌 Примечание", value=law['note'], inline=False)
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="вопрос", description="Задать вопрос ИИ-адвокату")
@app_commands.describe(question="Ваш вопрос")
async def ask_cmd(interaction: discord.Interaction, question: str):
    await interaction.response.defer()
    answer = await ask_ai(question)
    embed = discord.Embed(title="⚖️ ИИ-адвокат", description=answer, color=discord.Color.purple())
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="разделы_ук", description="Показать разделы УК")
async def uk_sections_cmd(interaction: discord.Interaction):
    embed = discord.Embed(title="📚 Разделы УК", color=discord.Color.red())
    for num, name in uk_sections.items():
        count = len([l for l in uk_laws if l["section"] == num])
        embed.add_field(name=f"Глава {num}", value=f"{name}\n└ {count} статей", inline=True)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="разделы_пк", description="Показать разделы ПК")
async def pk_sections_cmd(interaction: discord.Interaction):
    sections = {"III": "Меры процессуального принуждения", "IV": "Иные положения", "V": "Ходатайства и жалобы"}
    embed = discord.Embed(title="📚 Разделы ПК", color=discord.Color.green())
    for num, name in sections.items():
        count = len([l for l in pk_laws if l["article"] in ["15","16","17","19","20","22","28","29","31","33","36","9","12","56","М7"]])
        embed.add_field(name=f"Раздел {num}", value=f"{name}\n└ {count} статей", inline=True)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="справка", description="Все команды")
async def help_cmd(interaction: discord.Interaction):
    embed = discord.Embed(title="📚 Помощь", color=discord.Color.gold())
    embed.add_field(name="⚖️ УК", value="`/ук убийство`", inline=False)
    embed.add_field(name="📜 ПК", value="`/пк задержание`", inline=False)
    embed.add_field(name="🤖 ИИ", value="`/вопрос Твой вопрос`", inline=False)
    embed.add_field(name="📚 Разделы", value="`/разделы_ук`, `/разделы_пк`", inline=False)
    embed.add_field(name="💎 Премиум", value="`/status`, `/give` (админ)", inline=False)
    await interaction.response.send_message(embed=embed)

# Проверяем, что Flask-сервер запущен
print(f"Flask должен слушать порт 8080 на 0.0.0.0")

bot.run(TOKEN)
