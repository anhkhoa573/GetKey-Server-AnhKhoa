import sqlite3
import hashlib
import secrets
import string
from datetime import datetime, timedelta, date

DB_PATH = "keys.db"


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, created_at TEXT NOT NULL, last_reset TEXT NOT NULL)")
    conn.execute("CREATE TABLE IF NOT EXISTS sessions (id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT UNIQUE NOT NULL, user_id INTEGER NOT NULL, game TEXT NOT NULL, duration INTEGER NOT NULL, device_fp TEXT NOT NULL, status TEXT DEFAULT 'pending', created_at TEXT NOT NULL, verified_at TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS keys (id INTEGER PRIMARY KEY AUTOINCREMENT, key_plain TEXT NOT NULL, user_id INTEGER NOT NULL, device_fp TEXT NOT NULL, game TEXT NOT NULL, duration_hours INTEGER NOT NULL, created_at TEXT NOT NULL, expires_at TEXT NOT NULL, uses INTEGER DEFAULT 0, max_uses INTEGER DEFAULT 1)")
    conn.execute("CREATE TABLE IF NOT EXISTS daily_limits (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, day TEXT NOT NULL, count INTEGER DEFAULT 0, UNIQUE(user_id, day))")
    conn.commit()
    conn.close()


def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()


def create_user(username, password):
    init_db()
    if len(username) < 3 or len(username) > 20:
        return False, "Ten dang nhap 3-20 ky tu."
    if len(password) < 6:
        return False, "Mat khau it nhat 6 ky tu."
    conn = sqlite3.connect(DB_PATH)
    try:
        now = datetime.utcnow().isoformat()
        conn.execute("INSERT INTO users (username, password_hash, created_at, last_reset) VALUES (?, ?, ?, ?)",
                     (username, hash_password(password), now, date.today().isoformat()))
        conn.commit()
        conn.close()
        return True, "Dang ky thanh cong!"
    except sqlite3.IntegrityError:
        conn.close()
        return False, "Ten dang nhap da ton tai."


def authenticate(username, password):
    init_db()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM users WHERE username = ? AND password_hash = ?",
                       (username, hash_password(password))).fetchone()
    conn.close()
    return dict(row) if row else None


def generate_session_id():
    return secrets.token_urlsafe(24)


def create_session(user_id, game, duration, device_fp):
    init_db()
    session_id = generate_session_id()
    now = datetime.utcnow().isoformat()
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT INTO sessions (session_id, user_id, game, duration, device_fp, status, created_at) VALUES (?, ?, ?, ?, ?, 'pending', ?)",
                 (session_id, user_id, game, duration, device_fp, now))
    conn.commit()
    conn.close()
    return session_id


def get_session(session_id):
    init_db()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def mark_session_verified(session_id):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE sessions SET status = 'verified', verified_at = ? WHERE session_id = ?",
                 (datetime.utcnow().isoformat(), session_id))
    conn.commit()
    conn.close()


def generate_key():
    chars = string.ascii_uppercase + string.digits
    random_part = ''.join(secrets.choice(chars) for _ in range(8))
    return "ANHKHOA-" + random_part


def create_key_for_session(session_id, user_id, device_fp, game, duration):
    init_db()
    key_plain = generate_key()
    now = datetime.utcnow()
    expires = now + timedelta(hours=duration)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT INTO keys (key_plain, user_id, device_fp, game, duration_hours, created_at, expires_at, uses, max_uses) VALUES (?, ?, ?, ?, ?, ?, ?, 0, 1)",
                 (key_plain, user_id, device_fp, game, duration, now.isoformat(), expires.isoformat()))
    conn.commit()
    conn.close()
    return key_plain


def check_daily_limit(user_id):
    init_db()
    today = date.today().isoformat()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT count FROM daily_limits WHERE user_id = ? AND day = ?", (user_id, today)).fetchone()
    conn.close()
    used = row["count"] if row else 0
    remaining = max(0, 5 - used)
    return remaining > 0, used, remaining


def increment_daily_limit(user_id):
    init_db()
    today = date.today().isoformat()
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT INTO daily_limits (user_id, day, count) VALUES (?, ?, 1) ON CONFLICT(user_id, day) DO UPDATE SET count = count + 1",
                 (user_id, today))
    conn.commit()
    conn.close()


def validate_key(key, device_fp):
    init_db()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM keys WHERE key_plain = ?", (key,)).fetchone()
    if not row:
        conn.close()
        return False, "Key khong ton tai."
    if row["device_fp"] != device_fp:
        conn.close()
        return False, "Key da dung tren thiet bi khac."
    expires = datetime.fromisoformat(row["expires_at"])
    if datetime.utcnow() > expires:
        conn.close()
        return False, "Key da het han."
    if row["uses"] >= row["max_uses"]:
        conn.close()
        return False, "Key da het so lan su dung."
    conn.execute("UPDATE keys SET uses = uses + 1 WHERE id = ?", (row["id"],))
    conn.commit()
    conn.close()
    return True, "Key hop le!"
