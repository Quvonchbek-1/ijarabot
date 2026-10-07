"""
SQLite baza — main.py (e'lon joylash) va bot.py (to'lov/tarif) uchun umumiy.
Fayl: bot.db (eski housing.db / database.db bilan aralashmasligi uchun yangi nom).
"""

import os
import sqlite3
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.environ.get("DB_FILE", os.path.join(BASE_DIR, "bot.db"))
COUNTER_FILE = os.environ.get("COUNTER_FILE", os.path.join(BASE_DIR, "counter.txt"))
DT_FMT = "%Y-%m-%d %H:%M:%S"


def _conn():
    c = sqlite3.connect(DB_FILE, timeout=30)
    c.row_factory = sqlite3.Row
    return c


def init_db():
    with _conn() as c:
        c.execute("PRAGMA journal_mode=WAL")
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS offers (
                post_no   INTEGER PRIMARY KEY,
                olx_id    TEXT UNIQUE,
                title     TEXT,
                phone     TEXT,
                price     TEXT,
                location  TEXT,
                created_at TEXT
            );
            CREATE TABLE IF NOT EXISTS users (
                user_id    INTEGER PRIMARY KEY,
                username   TEXT,
                first_name TEXT,
                created_at TEXT
            );
            CREATE TABLE IF NOT EXISTS subscriptions (
                user_id    INTEGER PRIMARY KEY,
                expires_at TEXT
            );
            CREATE TABLE IF NOT EXISTS payments (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER,
                post_no    INTEGER,
                plan       TEXT,
                amount     INTEGER,
                file_id    TEXT,
                file_type  TEXT,
                status     TEXT DEFAULT 'pending',
                created_at TEXT
            );
            """
        )


# ---------------------------------------------------------------- E'LONLAR --

def _read_counter():
    try:
        with open(COUNTER_FILE, "r", encoding="utf-8") as f:
            return int(f.read().strip() or 0)
    except Exception:
        return 0


def next_post_no():
    """Keyingi e'lon raqami (#33 kabi). counter.txt va bazadagi eng kattasidan +1."""
    with _conn() as c:
        row = c.execute("SELECT MAX(post_no) AS m FROM offers").fetchone()
    return max(row["m"] or 0, _read_counter()) + 1


def save_offer(post_no, olx_id, title, phone, price, location):
    with _conn() as c:
        c.execute(
            "INSERT OR IGNORE INTO offers (post_no, olx_id, title, phone, price, location, created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (post_no, str(olx_id), title, phone, price, location,
             datetime.now().strftime(DT_FMT)),
        )
    if post_no > _read_counter():
        with open(COUNTER_FILE, "w", encoding="utf-8") as f:
            f.write(str(post_no))


def get_offer(post_no):
    with _conn() as c:
        return c.execute("SELECT * FROM offers WHERE post_no=?", (post_no,)).fetchone()


# ------------------------------------------------------------ FOYDALANUVCHI --

def upsert_user(user_id, username, first_name):
    with _conn() as c:
        c.execute(
            "INSERT INTO users (user_id, username, first_name, created_at) VALUES (?,?,?,?) "
            "ON CONFLICT(user_id) DO UPDATE SET username=excluded.username, first_name=excluded.first_name",
            (user_id, username or "", first_name or "", datetime.now().strftime(DT_FMT)),
        )


# ------------------------------------------------------------------- OBUNA --

def get_subscription(user_id):
    """Faol obuna tugash vaqti (datetime) yoki None."""
    with _conn() as c:
        row = c.execute("SELECT expires_at FROM subscriptions WHERE user_id=?", (user_id,)).fetchone()
    if not row:
        return None
    exp = datetime.strptime(row["expires_at"], DT_FMT)
    return exp if exp > datetime.now() else None


def grant_subscription(user_id, days):
    """Obunani uzaytiradi (faol bo'lsa — ustiga qo'shadi). Yangi tugash vaqtini qaytaradi."""
    now = datetime.now()
    current = get_subscription(user_id)
    start = current if current and current > now else now
    new_exp = start + timedelta(days=days)
    with _conn() as c:
        c.execute(
            "INSERT INTO subscriptions (user_id, expires_at) VALUES (?,?) "
            "ON CONFLICT(user_id) DO UPDATE SET expires_at=excluded.expires_at",
            (user_id, new_exp.strftime(DT_FMT)),
        )
    return new_exp


# ------------------------------------------------------------------ TO'LOV --

def create_payment(user_id, post_no, plan, amount, file_id, file_type):
    with _conn() as c:
        cur = c.execute(
            "INSERT INTO payments (user_id, post_no, plan, amount, file_id, file_type, status, created_at) "
            "VALUES (?,?,?,?,?,?, 'pending', ?)",
            (user_id, post_no, plan, amount, file_id, file_type,
             datetime.now().strftime(DT_FMT)),
        )
        return cur.lastrowid


def get_payment(payment_id):
    with _conn() as c:
        return c.execute("SELECT * FROM payments WHERE id=?", (payment_id,)).fetchone()


def set_payment_status(payment_id, status):
    with _conn() as c:
        c.execute("UPDATE payments SET status=? WHERE id=?", (status, payment_id))
