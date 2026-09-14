import sqlite3

def init_db():
    conn = sqlite3.connect('housing.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS offers (
            offer_id TEXT PRIMARY KEY,
            title TEXT,
            phone TEXT,
            price TEXT,
            location TEXT
        )
    ''')
    conn.commit()
    conn.close()

def save_offer(offer_id, title, phone, price, location):
    conn = sqlite3.connect('housing.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO offers (offer_id, title, phone, price, location)
        VALUES (?, ?, ?, ?, ?)
    ''', (str(offer_id), title, phone, str(price), location))
    conn.commit()
    conn.close()
