import sqlite3

def init_db():
    conn = sqlite3.connect('housing.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS offers (
            offer_id TEXT PRIMARY KEY,
            title TEXT,
            phone TEXT
        )
    ''')
    conn.commit()
    conn.close()

def save_offer(offer_id: str, title: str, phone: str):
    conn = sqlite3.connect('housing.db')
    cursor = conn.cursor()
    cursor.execute('INSERT OR REPLACE INTO offers VALUES (?, ?, ?)', (offer_id, title, phone))
    conn.commit()
    conn.close()

def get_phone_number(offer_id: str):
    conn = sqlite3.connect('housing.db')
    cursor = conn.cursor()
    cursor.execute('SELECT title, phone FROM offers WHERE offer_id = ?', (offer_id,))
    result = cursor.fetchone()
    conn.close()
    return result
