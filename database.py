import sqlite3
from datetime import datetime, timedelta
import os

DB_PATH = "premium.db"

def init_db():
    """Создаёт таблицу если её нет"""
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
    print("✅ База данных готова")

def set_premium(discord_id: str, days: int, telegram_id: str = None):
    """Активировать премиум по Discord ID"""
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
    print(f"✅ Премиум активирован для Discord ID {discord_id} на {days} дней")

def is_premium(discord_id: str) -> bool:
    """Проверить активен ли премиум"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT expires_at FROM premium_users WHERE discord_id = ?', (discord_id,))
    row = c.fetchone()
    conn.close()
    
    if row and row[0]:
        expires_at = datetime.fromisoformat(row[0])
        return expires_at > datetime.now()
    return False

def get_expiry(discord_id: str) -> str:
    """Получить дату окончания подписки"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT expires_at FROM premium_users WHERE discord_id = ?', (discord_id,))
    row = c.fetchone()
    conn.close()
    return row[0][:10] if row and row[0] else None

def get_all_premium() -> list:
    """Список всех активных подписок (для админа)"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT discord_id, expires_at FROM premium_users WHERE expires_at > ?', (datetime.now().isoformat(),))
    rows = c.fetchall()
    conn.close()
    return rows

def remove_premium(discord_id: str):
    """Удалить подписку (для админа)"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('DELETE FROM premium_users WHERE discord_id = ?', (discord_id,))
    conn.commit()
    conn.close()

# Создаём таблицу при импорте
init_db()
