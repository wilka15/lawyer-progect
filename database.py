import sqlite3
from datetime import datetime, timedelta

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
    print("✅ База данных инициализирована")

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
    print(f"✅ Премиум выдан Discord ID {discord_id} на {days} дней")

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

def get_discord_id_by_telegram(telegram_id: str) -> str:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT discord_id FROM premium_users WHERE telegram_id = ?', (telegram_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None

def link_accounts(discord_id: str, telegram_id: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('UPDATE premium_users SET telegram_id = ? WHERE discord_id = ?', (telegram_id, discord_id))
    conn.commit()
    conn.close()

def get_all_premium() -> list:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT discord_id, expires_at FROM premium_users WHERE expires_at > ?', (datetime.now().isoformat(),))
    rows = c.fetchall()
    conn.close()
    return rows

init_db()
