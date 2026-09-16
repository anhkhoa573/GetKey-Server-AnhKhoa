import sqlite3
import hashlib
import secrets
import string
from datetime import datetime, timedelta
from cryptography.fernet import Fernet
import os

DB_PATH = "keys.db"
KEY_FILE = ".fernet_key"


def get_fernet():
    if os.path.exists(KEY_FILE):
        with open(KEY_FILE, "rb") as f:
            key = f.read()
    else:
        key = Fernet.generate_key()
        with open(KEY_FILE, "wb") as f:
            f.write(key)
        try:
            os.chmod(KEY_FILE, 0o600)
        except:
            pass
    return Fernet(key)


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key_hash TEXT UNIQUE NOT NULL,
            key_encrypted TEXT NOT NULL,
            device_fp TEXT NOT NULL,
            game TEXT NOT NULL,
            duration_hours INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            uses INTEGER DEFAULT 0,
            max_uses INTEGER DEFAULT 1,
            service TEXT NOT NULL,
            session_id TEXT UNIQUE NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT UNIQUE NOT NULL,
            game TEXT NOT NULL,
            duration INTEGER NOT NULL,
            service TEXT NOT NULL,
            device_fp TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            created_at TEXT NOT NULL,
            verified_at TEXT
        )
    """)
    conn.commit()
    conn.close()


def generate_session_id():
    return secrets.token_urlsafe(24)


def create_session(game, duration, service, device_fp):
    init_db()
    session_id = generate_session_id()
    now = datetime.utcnow().isoformat()
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT INTO sessions (session_id, game, duration, service, device_fp, status, created_at)
        VALUES (?, ?, ?, ?, ?, 'pending', ?)
    """, (session_id, game, duration, service, device_fp, now))
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
    conn.execute("""
        UPDATE sessions SET status = 'verified', verified_at = ?
        WHERE session_id = ?
    """, (datetime.utcnow().isoformat(), session_id))
    conn.commit()
    conn.close()


def generate_key():
    chars = string.ascii_uppercase + string.digits
    random_part = ''.join(secrets.choice(chars) for _ in range(8))
    return f"ANHKHOA-{random_part}"


def hash_key(key):
    return hashlib.sha256(key.encode()).hexdigest()


def create_key(session_id, device_fp, game, duration, service):
    init_db()
    fernet = get_fernet()
    key_plain = generate_key()
    key_hash = hash_key(key_plain)
    key_enc = fernet.encrypt(key_plain.encode()).decode()
    now = datetime.utcnow()
    expires = now + timedelta(hours=duration)
    max_uses = 1 if duration == 12 else 2
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT INTO keys (key_hash, key_encrypted, device_fp, game, duration_hours,
                          created_at, expires_at, uses, max_uses, service, session_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?)
    """, (key_hash, key_enc, device_fp, game, duration, now.isoformat(),
          expires.isoformat(), max_uses, service, session_id))
    conn.commit()
    conn.close()
    return key_plain


def validate_key(key_plain, device_fp):
    init_db()
    key_hash = hash_key(key_plain)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM keys WHERE key_hash = ?", (key_hash,)).fetchone()
    if not row:
        conn.close()
        return False, "Key khong ton tai."
    if row["device_fp"] != device_fp:
        conn.close()
        return False, "Key da duoc dung tren thiet bi khac."
    expires = datetime.fromisoformat(row["expires_at"])
    if datetime.utcnow() > expires:
        conn.close()
        return False, "Key da het han."
    if row["uses"] >= row["max_uses"]:
        conn.close()
        return False, "Key da het so lan su dung."
    conn.execute("UPDATE keys SET uses = uses + 1 WHERE key_hash = ?", (key_hash,))
    conn.commit()
    conn.close()
    return True, "Key hop le!"
