import sqlite3
from datetime import datetime

DB_NAME = "database.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS offers (
            id TEXT PRIMARY KEY,
            title TEXT,
            phone TEXT,
            price_usd INTEGER,
            location TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            sub_until TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

def save_offer(offer_id, title, phone, price_usd, location):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO offers (id, title, phone, price_usd, location)
        VALUES (?, ?, ?, ?, ?)
    """, (offer_id, title, phone, price_usd, location))
    conn.commit()
    conn.close()

def get_offer(offer_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT title, phone, price_usd, location FROM offers WHERE id = ?", (offer_id,))
    row = cursor.fetchone()
    conn.close()
    return row

def is_user_subscribed(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT sub_until FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row and row[0]:
        sub_date = datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S")
        return sub_date > datetime.now()
    return False

if __name__ == "__main__":
    init_db()
