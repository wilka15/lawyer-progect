import discord
from discord.ext import commands
from discord import app_commands
import re
import os
from datetime import datetime, timedelta
from difflib import get_close_matches
from threading import Thread
from flask import Flask, request, jsonify
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
    
    # Общее количество пользователей
    c.execute('SELECT COUNT(*) FROM premium_users')
    total_users = c.fetchone()[0]
    
    # Количество активных подписок
    now = datetime.now().isoformat()
    c.execute('SELECT COUNT(*) FROM premium_users WHERE expires_at > ?', (now,))
    active_premium = c.fetchone()[0]
    
    # Всего запросов в этом месяце
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

# ========== ФУНКЦИИ ПРЕМИУМА И РЕФЕРАЛОВ ==========
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

# ========== ПОЛНЫЙ УК ==========
uk_laws = [
    {"article": "1", "title": "Уголовное законодательство", "penalty": "УК состоит из настоящего Кодекса", "stars": "📖", "note": ""},
    {"article": "1.2", "title": "Задачи Уголовного кодекса", "penalty": "Охрана прав и свобод, собственности, общественного порядка", "stars": "📖", "note": ""},
    {"article": "1.3", "title": "Принцип законности", "penalty": "Преступность деяния определяется только УК", "stars": "📖", "note": ""},
    {"article": "1.4", "title": "Принцип равенства граждан перед законом", "penalty": "Все равны независимо от пола, расы, имущественного положения", "stars": "📖", "note": ""},
    {"article": "1.5", "title": "Принцип вины", "penalty": "Ответственность только за виновные действия", "stars": "📖", "note": ""},
    {"article": "1.6", "title": "Принцип справедливости", "penalty": "Наказание должно соответствовать опасности преступления", "stars": "📖", "note": ""},
    {"article": "1.7", "title": "Принцип гуманизма", "penalty": "Наказание не может причинять физические страдания", "stars": "📖", "note": ""},
    {"article": "1.8", "title": "Основание уголовной ответственности", "penalty": "Совершение деяния, содержащего все признаки состава преступления", "stars": "📖", "note": ""},
    {"article": "1.9", "title": "Состав преступления", "penalty": "Совокупность объективных и субъективных признаков", "stars": "📖", "note": ""},
    {"article": "1.10", "title": "Судимость", "penalty": "Запрещает госслужбу", "stars": "📖", "note": ""},
    {"article": "1.11", "title": "Действие уголовного закона во времени", "penalty": "Закон, действовавший во время совершения", "stars": "📖", "note": ""},
    {"article": "1.12", "title": "Обратная сила уголовного закона", "penalty": "Закон, смягчающий наказание, имеет обратную силу", "stars": "📖", "note": ""},
    {"article": "2", "title": "Понятие преступления", "penalty": "Виновно совершенное общественно опасное деяние", "stars": "📖", "note": ""},
    {"article": "2.2", "title": "Рецидив преступлений", "penalty": "Совершение умышленного преступления при наличии судимости", "stars": "📖", "note": ""},
    {"article": "2.3", "title": "Формы вины", "penalty": "Умышленно или по неосторожности", "stars": "📖", "note": ""},
    {"article": "2.4", "title": "Умысел", "penalty": "Прямой или косвенный", "stars": "📖", "note": ""},
    {"article": "2.5", "title": "Неосторожность", "penalty": "Легкомыслие или небрежность", "stars": "📖", "note": ""},
    {"article": "2.6", "title": "Невиновное причинение вреда", "penalty": "Лицо не осознавало опасности своих действий", "stars": "📖", "note": ""},
    {"article": "3", "title": "Оконченное и неоконченное преступление", "penalty": "Приготовление, покушение, оконченное", "stars": "📖", "note": ""},
    {"article": "3.2", "title": "Приготовление и покушение", "penalty": "Действия, не доведённые до конца", "stars": "📖", "note": ""},
    {"article": "3.3", "title": "Добровольный отказ от преступления", "penalty": "Прекращение действий, если лицо осознавало возможность доведения", "stars": "📖", "note": ""},
    {"article": "3.4", "title": "Соучастие в преступлении", "penalty": "Умышленное совместное участие двух или более лиц", "stars": "📖", "note": ""},
    {"article": "3.5", "title": "Виды соучастников", "penalty": "Исполнитель, организатор, подстрекатель, пособник", "stars": "📖", "note": ""},
    {"article": "3.7", "title": "Группа лиц, ОПГ, преступное сообщество", "penalty": "Совершение преступления группой по предварительному сговору", "stars": "📖", "note": ""},
    {"article": "4", "title": "Необходимая оборона", "penalty": "Защита от посягательства, опасного для жизни", "stars": "📖", "note": ""},
    {"article": "4.2", "title": "Причинение вреда при задержании", "penalty": "Допустимо, если иными средствами задержать невозможно", "stars": "📖", "note": ""},
    {"article": "4.3", "title": "Крайняя необходимость", "penalty": "Устранение опасности, если она не могла быть устранена иначе", "stars": "📖", "note": ""},
    {"article": "4.4", "title": "Обоснованный риск", "penalty": "Достижение общественно полезной цели", "stars": "📖", "note": ""},
    {"article": "4.5", "title": "Исполнение приказа", "penalty": "Не является преступлением. Ответственность несёт отдавший приказ", "stars": "📖", "note": ""},
    {"article": "5", "title": "Виды наказаний", "penalty": "Штраф, лишение прав, увольнение, лишение свободы", "stars": "📖", "note": ""},
    {"article": "5.3", "title": "Общие начала назначения наказания", "penalty": "Учитываются характер опасности, личность виновного, смягчающие обстоятельства", "stars": "📖", "note": ""},
    {"article": "5.5", "title": "Смягчающие обстоятельства", "penalty": "Явка с повинной, примирение, помощь потерпевшему", "stars": "📖", "note": ""},
    {"article": "5.6", "title": "Отягчающие обстоятельства", "penalty": "Группа лиц, особая жестокость, рецидив", "stars": "📖", "note": ""},
    {"article": "5.7", "title": "Назначение более мягкого наказания", "penalty": "При исключительных обстоятельствах", "stars": "📖", "note": ""},
    {"article": "5.8", "title": "Освобождение от уголовной ответственности", "penalty": "Примирение сторон, судебный штраф", "stars": "📖", "note": ""},
    {"article": "5.9", "title": "Сроки давности", "penalty": "15 дней. Боло-розыск: от ★ до ★★★★★", "stars": "📖", "note": ""},
    {"article": "5.11", "title": "Добровольная сдача предметов", "penalty": "Освобождение от ответственности по ст.12.8,12.8.1,13.1,13.2", "stars": "📖", "note": ""},
    {"article": "5.12", "title": "Залог", "penalty": "$25.000 за 1 год", "stars": "📖", "note": ""},
    {"article": "6.1", "title": "Умышленное нанесение побоев", "penalty": "от 1 до 3 лет", "stars": "★★★", "note": ""},
    {"article": "6.2", "title": "Убийство", "penalty": "от 2 до 4 лет", "stars": "★★★★", "note": ""},
    {"article": "6.3", "title": "Тяжкое убийство", "penalty": "от 4 до 5 лет", "stars": "★★★★★", "note": ""},
    {"article": "6.4", "title": "Угроза убийством", "penalty": "от 2 до 3 лет, либо штраф $30.000-$50.000", "stars": "★★★", "note": ""},
    {"article": "6.5", "title": "Воспрепятствование деятельности медработника", "penalty": "от 2 до 3 лет, либо штраф $5.000-$20.000", "stars": "★★★", "note": ""},
    {"article": "7.1", "title": "Похищение человека", "penalty": "от 4 до 5 лет", "stars": "★★★★★", "note": ""},
    {"article": "7.1.1", "title": "Незаконное лишение свободы", "penalty": "от 3 до 4 лет", "stars": "★★★★", "note": ""},
    {"article": "7.2", "title": "Использование рабского труда", "penalty": "от 3 до 4 лет", "stars": "★★★★", "note": ""},
    {"article": "7.3", "title": "Купля-продажа человека", "penalty": "от 3 до 4 лет", "stars": "★★★★", "note": ""},
    {"article": "7.4", "title": "Клевета", "penalty": "от 2 до 3 лет, либо штраф $40.000-$80.000", "stars": "★★★", "note": ""},
    {"article": "7.4.1", "title": "Клевета с обвинением в преступлении", "penalty": "от 2 до 3 лет, либо штраф $40.000-$80.000", "stars": "★★★", "note": ""},
    {"article": "8.1", "title": "Изнасилование", "penalty": "от 3 до 4 лет", "stars": "★★★★", "note": ""},
    {"article": "8.2", "title": "Понуждение к половому акту", "penalty": "от 2 до 3 лет", "stars": "★★★", "note": ""},
    {"article": "8.3", "title": "Сексуальное домогательство", "penalty": "от 2 до 3 лет", "stars": "★★★", "note": ""},
    {"article": "9.1", "title": "Воспрепятствование избирательным правам", "penalty": "от 3 до 5 лет", "stars": "★★★★★", "note": ""},
    {"article": "9.2", "title": "Воспрепятствование прибытию сенатора", "penalty": "от 1 до 3 лет, либо штраф $20.000", "stars": "★★★", "note": ""},
    {"article": "9.2.1", "title": "Срыв заседания Сената", "penalty": "от 1 до 3 лет", "stars": "★★★", "note": ""},
    {"article": "10.1", "title": "Кража", "penalty": "от 2 до 3 лет", "stars": "★★★", "note": ""},
    {"article": "10.2", "title": "Мошенничество", "penalty": "от 2 до 3 лет", "stars": "★★★", "note": ""},
    {"article": "10.2.1", "title": "Вымогательство", "penalty": "от 2 до 3 лет", "stars": "★★★", "note": ""},
    {"article": "10.3", "title": "Грабеж", "penalty": "от 2 до 3 лет", "stars": "★★★", "note": ""},
    {"article": "10.4", "title": "Разбой", "penalty": "от 2 до 4 лет", "stars": "★★★★", "note": ""},
    {"article": "10.5", "title": "Угон авто", "penalty": "от 1 до 3 лет", "stars": "★★★", "note": ""},
    {"article": "10.5.1", "title": "Угон гос. транспорта", "penalty": "от 3 до 4 лет", "stars": "★★★★", "note": ""},
    {"article": "10.6", "title": "Уничтожение чужого имущества", "penalty": "от 1 до 3 лет, либо штраф $20.000-$60.000", "stars": "★★★", "note": ""},
    {"article": "10.7", "title": "Уничтожение чужого имущества (альт.)", "penalty": "от 2 до 3 лет, либо штраф $30.000-$60.000", "stars": "★★★", "note": ""},
    {"article": "10.8", "title": "Уничтожение госимущества", "penalty": "от 2 до 3 лет, либо штраф $40.000-$70.000", "stars": "★★★", "note": ""},
    {"article": "10.9", "title": "Проникновение в жилище", "penalty": "от 3 до 4 лет", "stars": "★★★★", "note": ""},
    {"article": "11.1", "title": "Предпринимательство без регистрации", "penalty": "от 1 до 3 лет, либо штраф $50.000-$100.000", "stars": "★★★", "note": ""},
    {"article": "11.2", "title": "Принуждение к сделке", "penalty": "от 2 до 3 лет", "stars": "★★★", "note": ""},
    {"article": "11.3", "title": "Уклонение от налогов", "penalty": "взыскание ×2 + от 3 до 5 лет", "stars": "★★★★★", "note": ""},
    {"article": "11.4", "title": "Сокрытие средств от налогов", "penalty": "от 2 до 3 лет, либо взыскание ×2", "stars": "★★★", "note": ""},
    {"article": "11.5", "title": "Ограничение конкуренции", "penalty": "от 2 до 4 лет", "stars": "★★★★", "note": ""},
    {"article": "11.6", "title": "Финансовые махинации с госфинансированием", "penalty": "от 4 до 5 лет", "stars": "★★★★★", "note": ""},
    {"article": "11.7", "title": "Финансирование экстремистской деятельности", "penalty": "от 4 до 5 лет", "stars": "★★★★★", "note": ""},
    {"article": "12.1", "title": "Терроризм", "penalty": "от 4 до 5 лет", "stars": "★★★★★", "note": ""},
    {"article": "12.1.1", "title": "Публичные призывы к терроризму", "penalty": "от 4 до 5 лет", "stars": "★★★★★", "note": ""},
    {"article": "12.2", "title": "Ложное сообщение о теракте", "penalty": "от 3 до 4 лет", "stars": "★★★★", "note": ""},
    {"article": "12.3", "title": "Неоднократные админ. правонарушения", "penalty": "от 1 до 2 лет, либо штраф $20.000", "stars": "★★", "note": ""},
    {"article": "12.4", "title": "Возбуждение ненависти или вражды", "penalty": "от 4 до 5 лет", "stars": "★★★★★", "note": ""},
    {"article": "12.5", "title": "Организация экстремистской организации", "penalty": "от 4 до 5 лет", "stars": "★★★★★", "note": ""},
    {"article": "12.6", "title": "Нарушение порядка публичного мероприятия", "penalty": "от 2 до 3 лет", "stars": "★★★", "note": ""},
    {"article": "12.6.1", "title": "Организация массовых беспорядков", "penalty": "от 3 до 5 лет", "stars": "★★★★★", "note": ""},
    {"article": "12.7", "title": "Проникновение на закрытую территорию", "penalty": "от 1 до 3 лет, либо штраф $20.000-$50.000", "stars": "★★★", "note": ""},
    {"article": "12.7.1", "title": "Проникновение на особо охраняемую территорию", "penalty": "от 4 до 5 лет, либо штраф $50.000-$100.000", "stars": "★★★★★", "note": ""},
    {"article": "12.7.2", "title": "Проникновение на территорию оцепления", "penalty": "от 4 до 5 лет, либо штраф $50.000-$100.000", "stars": "★★★★★", "note": ""},
    {"article": "12.8", "title": "Незаконное хранение оружия", "penalty": "от 3 до 4 лет, либо штраф $20.000-$60.000", "stars": "★★★★", "note": ""},
    {"article": "12.8.1", "title": "Оружие гособразца у гражданских", "penalty": "от 3 до 5 лет", "stars": "★★★★★", "note": ""},
    {"article": "12.8.2", "title": "Незаконное ношение гранат", "penalty": "от 4 до 5 лет, либо штраф $60.000-$100.000", "stars": "★★★★★", "note": ""},
    {"article": "12.9", "title": "Незаконный оборот взрывчатки", "penalty": "от 4 до 5 лет", "stars": "★★★★★", "note": ""},
    {"article": "12.10", "title": "Хищение оружия", "penalty": "от 3 до 4 лет", "stars": "★★★★", "note": ""},
    {"article": "12.10.1", "title": "Хищение оружия со склада улик сотрудниками", "penalty": "от 4 до 5 лет", "stars": "★★★★★", "note": ""},
    {"article": "12.11", "title": "Создание вооружённого формирования", "penalty": "от 4 до 5 лет", "stars": "★★★★★", "note": ""},
    {"article": "12.12", "title": "Создание преступного сообщества (ОПГ)", "penalty": "5 лет", "stars": "★★★★★", "note": ""},
    {"article": "12.13", "title": "Незаконное получение гостайны", "penalty": "от 4 до 5 лет", "stars": "★★★★★", "note": ""},
    {"article": "12.14", "title": "Хулиганство", "penalty": "до 2 лет, либо штраф $30.000-$40.000", "stars": "★★", "note": ""},
    {"article": "13.1", "title": "Кустарное производство наркотиков", "penalty": "от 2 до 4 лет", "stars": "★★★★", "note": ""},
    {"article": "13.2", "title": "Сбыт наркотиков", "penalty": "от 3 до 5 лет", "stars": "★★★★★", "note": ""},
    {"article": "13.3", "title": "Хранение наркотиков от 5 грамм", "penalty": "от 2 до 4 лет", "stars": "★★★★", "note": ""},
    {"article": "13.4", "title": "Хранение наркотиков от 20 грамм", "penalty": "от 4 до 5 лет", "stars": "★★★★★", "note": ""},
    {"article": "13.5", "title": "Наркотики у госслужащих", "penalty": "от 3 до 5 лет", "stars": "★★★★★", "note": ""},
    {"article": "14.1", "title": "Дискредитация госорганов", "penalty": "от 2 до 5 лет", "stars": "★★★★★", "note": ""},
    {"article": "14.2", "title": "Насильственный захват власти", "penalty": "от 4 до 5 лет", "stars": "★★★★★", "note": ""},
    {"article": "14.2.1", "title": "Сепаратизм", "penalty": "от 4 до 5 лет", "stars": "★★★★★", "note": ""},
    {"article": "14.3", "title": "Разглашение гостайны", "penalty": "от 3 до 4 лет", "stars": "★★★★", "note": ""},
    {"article": "14.3.1", "title": "Незаконное получение гостайны", "penalty": "от 3 до 4 лет", "stars": "★★★★", "note": ""},
    {"article": "15.1", "title": "Превышение должностных полномочий", "penalty": "от 3 до 5 лет, либо штраф $75.000-$100.000", "stars": "★★★★★", "note": ""},
    {"article": "15.1.1", "title": "Злоупотребление должностными полномочиями", "penalty": "от 3 до 5 лет, либо штраф $50.000-$100.000", "stars": "★★★★★", "note": ""},
    {"article": "15.2", "title": "Неисполнение приказа руководителя", "penalty": "от 2 до 4 лет, либо штраф $50.000-$70.000", "stars": "★★★★", "note": ""},
    {"article": "15.3", "title": "Присвоение полномочий должностного лица", "penalty": "от 2 до 4 лет", "stars": "★★★★", "note": ""},
    {"article": "15.4", "title": "Получение взятки", "penalty": "от 4 до 5 лет", "stars": "★★★★★", "note": ""},
    {"article": "15.5", "title": "Дача взятки", "penalty": "от 4 до 5 лет", "stars": "★★★★★", "note": ""},
    {"article": "15.5.1", "title": "Посредничество во взяточничестве", "penalty": "от 4 до 5 лет", "stars": "★★★★★", "note": ""},
    {"article": "15.6", "title": "Халатность", "penalty": "от 2 до 5 лет, либо штраф $40.000-$70.000", "stars": "★★★★★", "note": ""},
    {"article": "15.7", "title": "Деструктивное поведение госслужащего", "penalty": "от 1 до 3 лет, либо штраф $30.000-$70.000", "stars": "★★★", "note": ""},
    {"article": "16.1", "title": "Вмешательство в деятельность суда", "penalty": "от 3 до 4 лет", "stars": "★★★★", "note": ""},
    {"article": "16.1.2", "title": "Воспрепятствование работе прокурора", "penalty": "от 3 до 4 лет, либо штраф $50.000-$100.000", "stars": "★★★★", "note": ""},
    {"article": "16.1.3", "title": "Неуважение к суду", "penalty": "от 2 до 5 лет, либо штраф $30.000-$50.000", "stars": "★★★★★", "note": ""},
    {"article": "16.2", "title": "Угроза судье или прокурору", "penalty": "от 4 до 5 лет", "stars": "★★★★★", "note": ""},
    {"article": "16.3", "title": "Привлечение невиновного", "penalty": "от 3 до 5 лет", "stars": "★★★★★", "note": ""},
    {"article": "16.4", "title": "Незаконное задержание", "penalty": "от 3 до 5 лет", "stars": "★★★★★", "note": ""},
    {"article": "16.5", "title": "Фальсификация доказательств", "penalty": "от 4 до 5 лет", "stars": "★★★★★", "note": ""},
    {"article": "16.8", "title": "Ложные показания в суде", "penalty": "от 3 до 4 лет", "stars": "★★★★", "note": ""},
    {"article": "16.9", "title": "Подкуп свидетеля", "penalty": "от 3 до 4 лет", "stars": "★★★★", "note": ""},
    {"article": "16.10", "title": "Неисполнение судебного акта", "penalty": "от 2 до 4 лет, либо штраф $30.000-$70.000", "stars": "★★★★", "note": ""},
    {"article": "16.10.1", "title": "Неисполнение судебных актов сотрудником", "penalty": "от 3 до 5 лет, либо штраф $40.000-$80.000", "stars": "★★★★★", "note": ""},
    {"article": "16.11", "title": "Сокрытие улик", "penalty": "от 3 до 4 лет", "stars": "★★★★", "note": ""},
    {"article": "16.12", "title": "Уклонение от расследования", "penalty": "от 3 до 4 лет", "stars": "★★★★", "note": ""},
    {"article": "16.15", "title": "Побег из тюрьмы", "penalty": "от 1 до 5 лет", "stars": "★..★★★★★", "note": ""},
    {"article": "16.16", "title": "Ложный донос", "penalty": "от 2 до 4 лет, либо штраф $40.000-$80.000", "stars": "★★★★", "note": ""},
    {"article": "17.1", "title": "Посягательство на жизнь полицейского", "penalty": "от 4 до 5 лет", "stars": "★★★★★", "note": ""},
    {"article": "17.2", "title": "Насилие в отношении полицейского", "penalty": "от 3 до 4 лет", "stars": "★★★★", "note": ""},
    {"article": "17.3", "title": "Оскорбление полицейского", "penalty": "от 1 до 3 лет, либо штраф $20.000-$50.000", "stars": "★★★", "note": ""},
    {"article": "17.4", "title": "Провокация госслужащего", "penalty": "штраф $5.000-$20.000 или до 3 лет", "stars": "★★★", "note": ""},
    {"article": "17.5", "title": "Самоуправство", "penalty": "от 2 до 3 лет", "stars": "★★★", "note": ""},
    {"article": "17.6", "title": "Неповиновение законному требованию", "penalty": "от 2 до 3 лет, либо штраф $20.000-$60.000", "stars": "★★★", "note": ""},
    {"article": "17.7", "title": "Отказ от оплаты штрафа", "penalty": "от 2 до 3 лет, либо штраф $20.000-$60.000", "stars": "★★★", "note": ""},
    {"article": "17.8", "title": "Подделка удостоверения", "penalty": "от 3 до 4 лет", "stars": "★★★★", "note": ""},
    {"article": "17.9", "title": "Оскорбление человека в общественном месте", "penalty": "до 2 лет", "stars": "★★", "note": ""},
    {"article": "17.10", "title": "Управление ТС с поддельной накладной", "penalty": "до 3 лет, либо штраф $50.000-$70.000", "stars": "★★★★", "note": ""},
    {"article": "18.1", "title": "Неисполнение приказа начальника", "penalty": "от 2 до 3 лет, либо увольнение, либо штраф $10.000-$35.000", "stars": "★★★", "note": ""},
    {"article": "18.2", "title": "Самовольное оставление части", "penalty": "от 2 до 3 лет, либо увольнение, либо штраф $10.000-$40.000", "stars": "★★★", "note": ""},
    {"article": "18.3", "title": "Дезертирство", "penalty": "от 3 до 4 лет, либо увольнение, либо штраф $25.000-$60.000", "stars": "★★★★", "note": ""},
    {"article": "18.4", "title": "Нарушение правил боевого дежурства", "penalty": "от 2 до 3 лет, либо увольнение, либо штраф $20.000-$35.000", "stars": "★★★", "note": ""},
    {"article": "18.5", "title": "Уничтожение оружия", "penalty": "от 2 до 3 лет, либо увольнение, либо штраф $25.000-$50.000", "stars": "★★★", "note": ""},
    {"article": "18.5.1", "title": "Уничтожение оружия по неосторожности", "penalty": "от 2 до 4 лет, либо увольнение, либо штраф $5.000-$35.000", "stars": "★★★★", "note": ""},
    {"article": "18.6", "title": "Нарушение правил вождения военной техники", "penalty": "от 2 до 4 лет, либо увольнение, либо штраф $40.000-$70.000", "stars": "★★★★", "note": ""},
    {"article": "19.1", "title": "Браконьерство", "penalty": "от 1 до 3 лет", "stars": "★★★", "note": ""},
    {"article": "19.2", "title": "Жестокое обращение с животным", "penalty": "от 2 до 4 лет, либо штраф $30.000-$80.000", "stars": "★★★", "note": ""},
]

# ========== ПОЛНЫЙ ПК ==========
pk_laws = [
    {"article": "1", "title": "Цели Процессуального кодекса", "penalty": "Защита прав и законных интересов", "stars": "📜", "note": ""},
    {"article": "2", "title": "Законность при производстве", "penalty": "Суд, прокурор, сотрудники не вправе применять закон, противоречащий ПК", "stars": "📜", "note": ""},
    {"article": "3", "title": "Уважение чести и достоинства", "penalty": "Запрещены унижение, пытки, жестокое обращение", "stars": "📜", "note": ""},
    {"article": "4", "title": "Неприкосновенность жилища", "penalty": "Осмотр — с согласия. Обыск — с ордером или в исключительных случаях", "stars": "📜", "note": ""},
    {"article": "5", "title": "Тайна переписки", "penalty": "Ограничение только на основании судебного акта", "stars": "📜", "note": ""},
    {"article": "6", "title": "Презумпция невиновности", "penalty": "Обвиняемый считается невиновным, пока его вина не доказана", "stars": "📜", "note": ""},
    {"article": "7", "title": "Свобода оценки доказательств", "penalty": "Судья оценивает по внутреннему убеждению", "stars": "📜", "note": ""},
    {"article": "8", "title": "Охрана прав и свобод", "penalty": "Обязаны разъяснять права, обеспечивать безопасность", "stars": "📜", "note": ""},
    {"article": "9", "title": "Право на обжалование", "penalty": "48 часов с момента задержания", "stars": "📜", "note": ""},
    {"article": "10", "title": "Неприкосновенность личности", "penalty": "Задержание только при законных основаниях", "stars": "📜", "note": ""},
    {"article": "11", "title": "Доказательства", "penalty": "Показания, экспертиза, вещдоки, протоколы, боло-розыск", "stars": "📜", "note": ""},
    {"article": "12", "title": "Недопустимые доказательства", "penalty": "Показания до прав, слухи, улики добытые незаконно", "stars": "📜", "note": ""},
    {"article": "15", "title": "Задержание", "penalty": "Срок до 1 часа", "stars": "⏰", "note": ""},
    {"article": "16", "title": "Основания задержания", "penalty": "На месте, следы, 3 свидетеля, фото/видео, ордер, ориентировка, боло-розыск", "stars": "🔍", "note": ""},
    {"article": "17", "title": "Порядок задержания", "penalty": "Наручники → представиться → Миранда → обыск → объяснить → доставить → проверить документы → фоторобот → допрос → предложить права → реализовать права", "stars": "📋", "note": ""},
    {"article": "19", "title": "Задержание госслужащего", "penalty": "Уведомить руководство и прокуратуру. Если прокурор не прибыл за 20 минут — освободить", "stars": "👮", "note": ""},
    {"article": "20", "title": "Освобождение подозреваемого", "penalty": "Не подтвердилось, нет лишения свободы, нарушен порядок, прошёл час, неприкосновенность", "stars": "🔓", "note": ""},
    {"article": "22", "title": "Права задержанного", "penalty": "Адвокат, молчание, ходатайства, встреча с адвокатом (10 мин), звонок (3 мин)", "stars": "📜", "note": ""},
    {"article": "26", "title": "Арест", "penalty": "Лишение свободы на срок по УК", "stars": "🔒", "note": ""},
    {"article": "27", "title": "Порядок ареста", "penalty": "Вторичный обыск → боло-розыск (1 год = 1 уровень) → объяснить → в КПЗ", "stars": "📋", "note": ""},
    {"article": "28", "title": "Личный обыск", "penalty": "Только при задержании или аресте", "stars": "🔎", "note": ""},
    {"article": "29", "title": "Обыск транспорта", "penalty": "Обыск только с ордером", "stars": "🚗", "note": ""},
    {"article": "31", "title": "Видеофиксация", "penalty": "Обязательная запись, хранение 48 часов", "stars": "🎥", "note": ""},
    {"article": "33", "title": "Залог", "penalty": "от $25.000 + $25.000 за уровень розыска", "stars": "💰", "note": ""},
    {"article": "36", "title": "Применение силы", "penalty": "1. Присутствие 2. Приказ 3. Физ. сила 4. Спецсредства 5. Огнестрельное оружие", "stars": "💪", "note": ""},
    {"article": "56", "title": "Допрос", "penalty": "Не более 1 часа. Адвокат присутствует, может потребовать 5-минутный перерыв", "stars": "👨‍⚖️", "note": ""},
    {"article": "М7", "title": "Правило Миранды", "penalty": "«Вы имеете право хранить молчание. Всё, что скажете, может быть использовано против вас. Вы имеете право на адвоката»", "stars": "📢", "note": ""},
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

# ========== ПРЕФИКСНЫЕ КОМАНДЫ ==========
@bot.command(name="ук")
async def uk_prefix(ctx, *, query: str):
    user_id = str(ctx.author.id)
    available, remaining, used = check_and_increment(user_id)
    if not available:
        await ctx.send(f"❌ У вас закончились бесплатные запросы! ({used}/5)\n🎁 Пригласите друга: `/реф` → +5 запросов\n💎 Купите премиум: @lawyer_pay_bot")
        return
    results = smart_search(query, uk_laws)
    if not results:
        await ctx.send(f"❌ Ничего не найдено по `{query}`")
        return
    if len(results) > 1:
        await ctx.send(f"🔍 Найдено {len(results)} статей: {', '.join([r['article'] for r in results[:5]])}")
        return
    law = results[0]
    embed = discord.Embed(title=f"⚖️ Ст {law['article']} УК", description=f"**{law['title']}**\n{law['stars']}", color=discord.Color.red())
    embed.add_field(name="📝 Наказание/Содержание", value=law['penalty'], inline=False)
    if law['note']:
        embed.add_field(name="📌 Примечание", value=law['note'], inline=False)
    await ctx.send(embed=embed)

@bot.command(name="пк")
async def pk_prefix(ctx, *, query: str):
    user_id = str(ctx.author.id)
    available, remaining, used = check_and_increment(user_id)
    if not available:
        await ctx.send(f"❌ У вас закончились бесплатные запросы! ({used}/5)\n🎁 Пригласите друга: `/реф` → +5 запросов\n💎 Купите премиум: @lawyer_pay_bot")
        return
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
    if law['note']:
        embed.add_field(name="📌 Примечание", value=law['note'], inline=False)
    await ctx.send(embed=embed)

@bot.command(name="статус")
async def status_prefix(ctx):
    user_id = str(ctx.author.id)
    used, bonus = get_user_requests(user_id)
    total = 5 + bonus
    remaining = get_remaining_free_requests(user_id)
    if is_premium(user_id):
        expiry = get_premium_expiry(user_id)
        await ctx.send(f"💎 Премиум активен до {expiry}\n📊 Запросов в месяце: {used}/{total} (безлимит)")
    else:
        await ctx.send(f"📊 Статистика:\n• Использовано: {used}/{total}\n• Осталось: {remaining}\n\n🎁 Пригласите друга: `/реф` → +5 запросов\n💎 Купите премиум: @lawyer_pay_bot")

@bot.command(name="реф")
async def ref_prefix(ctx):
    user_id = str(ctx.author.id)
    if get_invited_by(user_id):
        await ctx.send(f"❌ Вы уже были приглашены")
        return
    count = get_referral_count(user_id)
    code = f"!ref_{user_id}"
    await ctx.send(f"🌟 **Ваша реферальная ссылка:** `{code}`\n👥 Приглашено: {count}\n🎁 За каждого друга вы получаете +14 дней премиума!")

# ========== СЛЭШ-КОМАНДЫ ==========
@bot.tree.command(name="ук", description="Поиск по Уголовному кодексу")
@app_commands.describe(query="Номер статьи или название")
async def uk_cmd(interaction: discord.Interaction, query: str):
    user_id = str(interaction.user.id)
    available, remaining, used = check_and_increment(user_id)
    if not available:
        await interaction.response.send_message(f"❌ У вас закончились бесплатные запросы! ({used}/5)\n💎 Купите премиум: @lawyer_pay_bot", ephemeral=True)
        return
    await interaction.response.defer()
    results = smart_search(query, uk_laws)
    if not results:
        await interaction.followup.send(f"❌ Ничего не найдено по `{query}`")
        return
    if len(results) > 1:
        embed = discord.Embed(title=f"🔍 Найдено {len(results)} статей", color=discord.Color.orange())
        for law in results[:5]:
            embed.add_field(name=f"Ст.{law['article']} {law['stars']}", value=f"{law['title']}", inline=False)
        await interaction.followup.send(embed=embed)
        return
    law = results[0]
    embed = discord.Embed(title=f"⚖️ Ст {law['article']} УК", description=f"**{law['title']}**\n{law['stars']}", color=discord.Color.red())
    embed.add_field(name="📝 Наказание/Содержание", value=law['penalty'], inline=False)
    if law['note']:
        embed.add_field(name="📌 Примечание", value=law['note'], inline=False)
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="пк", description="Поиск по Процессуальному кодексу")
@app_commands.describe(query="Номер статьи или тема")
async def pk_cmd(interaction: discord.Interaction, query: str):
    user_id = str(interaction.user.id)
    available, remaining, used = check_and_increment(user_id)
    if not available:
        await interaction.response.send_message(f"❌ У вас закончились бесплатные запросы! ({used}/5)\n💎 Купите премиум: @lawyer_pay_bot", ephemeral=True)
        return
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

@bot.tree.command(name="статус", description="Проверить статус подписки")
async def status_cmd(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    used, bonus = get_user_requests(user_id)
    total = 5 + bonus
    remaining = get_remaining_free_requests(user_id)
    if is_premium(user_id):
        expiry = get_premium_expiry(user_id)
        embed = discord.Embed(title="💎 Статус", description=f"✅ Премиум активен до {expiry}\n📊 Запросов: {used}/{total} (безлимит)", color=discord.Color.green())
    else:
        embed = discord.Embed(title="💎 Статус", description=f"📊 Запросов: {used}/{total} осталось {remaining}\n\n🎁 Пригласите друга: `/реф`\n💎 Купите премиум: @lawyer_pay_bot", color=discord.Color.orange())
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="реф", description="Реферальная программа")
async def ref_cmd(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    if get_invited_by(user_id):
        await interaction.response.send_message("❌ Вы уже были приглашены", ephemeral=True)
        return
    count = get_referral_count(user_id)
    code = f"!ref_{user_id}"
    embed = discord.Embed(title="🌟 Реферальная программа", description=f"**Ваша ссылка:** `{code}`\n👥 Приглашено: {count}\n🎁 За друга: +14 дней премиума вам, +5 запросов другу", color=discord.Color.gold())
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="give_premium", description="[АДМИН] Выдать премиум")
@app_commands.describe(user="Пользователь", days="Количество дней")
async def give_premium_cmd(interaction: discord.Interaction, user: discord.User, days: int = 30):
    if not is_owner(interaction):
        await interaction.response.send_message("❌ Нет прав!", ephemeral=True)
        return
    set_premium(str(user.id), days)
    embed = discord.Embed(title="✅ Премиум выдан", description=f"{user.mention} получил премиум на {days} дней.", color=discord.Color.green())
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="premium_list", description="[АДМИН] Список активных подписок")
async def premium_list_cmd(interaction: discord.Interaction):
    if not is_owner(interaction):
        await interaction.response.send_message("❌ Нет прав!", ephemeral=True)
        return
    users = get_all_premium_users()
    if not users:
        await interaction.response.send_message("Нет активных подписок", ephemeral=True)
        return
    embed = discord.Embed(title=f"💎 Активные подписки ({len(users)})", color=discord.Color.gold())
    for discord_id, expires_at in users[:20]:
        try:
            user = await bot.fetch_user(int(discord_id))
            name = user.name
        except:
            name = f"ID: {discord_id}"
        days_left = (datetime.fromisoformat(expires_at) - datetime.now()).days
        embed.add_field(name=name, value=f"До: {expires_at[:10]} ({days_left} дн.)\n🆔 `{discord_id}`", inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="справка", description="Все команды")
async def help_cmd(interaction: discord.Interaction):
    embed = discord.Embed(title="📚 Помощь", color=discord.Color.gold())
    embed.add_field(name="⚖️ УК", value="`/ук убийство` или `!ук убийство`", inline=False)
    embed.add_field(name="📜 ПК", value="`/пк задержание` или `!пк задержание`", inline=False)
    embed.add_field(name="💎 Премиум", value="`/статус` или `!статус`", inline=False)
    embed.add_field(name="🌟 Рефералы", value="`/реф` или `!реф`", inline=False)
    embed.add_field(name="👑 Админ", value="`/give_premium`, `/premium_list`", inline=False)
    await interaction.response.send_message(embed=embed)

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    if isinstance(message.channel, discord.DMChannel):
        text = message.content.strip()
        if text.startswith("!ref_"):
            inviter_id = text.replace("!ref_", "")
            invited_id = str(message.author.id)
            if invited_id == inviter_id:
                await message.reply("❌ Нельзя активировать свою ссылку!")
                return
            if get_invited_by(invited_id):
                await message.reply("❌ Вы уже активировали чью-то ссылку!")
                return
            add_referral(invited_id, inviter_id)
            await message.reply(f"✅ Реферальный код активирован! Вы получили +5 бонусных запросов!\nВаш друг получил +14 дней премиума!")
            try:
                inviter = await bot.fetch_user(int(inviter_id))
                if inviter:
                    await inviter.send(f"🎉 Пользователь {message.author.name} активировал вашу реферальную ссылку! Вы получили +14 дней премиума!")
            except:
                pass
            return
    await bot.process_commands(message)

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
