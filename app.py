from flask import Flask, render_template, request, jsonify, redirect, url_for, session
import hashlib
import secrets
import string
import sqlite3
import os
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = "anhkhoa-secret-key-2024-change-me"
app.permanent_session_lifetime = timedelta(days=1)

DB_PATH = "keys.db"

# ============================================================
# CAU HINH
# ============================================================
LINK4M_URL = "https://link4m.net/ov9vn2T9"
CALLBACK_URL = "https://getkey-server-anhkhoa.onrender.com/callback"
# ============================================================


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key_hash TEXT UNIQUE NOT NULL,
            key_plain TEXT NOT NULL,
            device_fp TEXT NOT NULL,
            game TEXT NOT NULL,
            duration_hours INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            uses INTEGER DEFAULT 0,
            max_uses INTEGER DEFAULT 1
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT UNIQUE NOT NULL,
            game TEXT NOT NULL,
            duration INTEGER NOT NULL,
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


def generate_key():
    chars = string.ascii_uppercase + string.digits
    random_part = ''.join(secrets.choice(chars) for _ in range(8))
    return "ANHKHOA-" + random_part


def hash_key(key):
    return hashlib.sha256(key.encode()).hexdigest()


def create_session(game, duration, device_fp):
    init_db()
    session_id = generate_session_id()
    now = datetime.utcnow().isoformat()
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT INTO sessions (session_id, game, duration, device_fp, status, created_at)
        VALUES (?, ?, ?, ?, 'pending', ?)
    """, (session_id, game, duration, device_fp, now))
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


def create_key_for_session(session_id, device_fp, game, duration):
    init_db()
    key_plain = generate_key()
    key_hash = hash_key(key_plain)
    now = datetime.utcnow()
    expires = now + timedelta(hours=duration)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT INTO keys (key_hash, key_plain, device_fp, game, duration_hours,
                          created_at, expires_at, uses, max_uses)
        VALUES (?, ?, ?, ?, ?, ?, ?, 0, 1)
    """, (key_hash, key_plain, device_fp, game, duration, now.isoformat(), expires.isoformat()))
    conn.commit()
    conn.close()
    return key_plain


def get_device_fingerprint(req):
    ip = req.remote_addr or "unknown"
    ua = req.headers.get("User-Agent", "")
    combined = ip + "|" + ua
    return hashlib.sha256(combined.encode()).hexdigest()[:32]


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/start", methods=["POST"])
def api_start():
    data = request.get_json()
    game = data.get("game", "freefire")
    duration = 24

    device_fp = get_device_fingerprint(request)
    session_id = create_session(game, duration, device_fp)

    session["pending_session"] = session_id
    session["device_fp"] = device_fp
    session.permanent = True

    return jsonify({
        "ok": True,
        "session_id": session_id,
        "bypass_url": LINK4M_URL
    })


@app.route("/callback")
def callback():
    device_fp = session.get("device_fp") or get_device_fingerprint(request)
    session_id = session.get("pending_session", "")

    if not session_id:
        session_id = request.args.get("session", "")

    if not session_id:
        return redirect(url_for("index"))

    session_data = get_session(session_id)
    if not session_data:
        return redirect(url_for("index"))

    if session_data["status"] == "verified":
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT key_plain FROM keys WHERE device_fp = ? ORDER BY id DESC LIMIT 1",
            (device_fp,)
        ).fetchone()
        conn.close()
        if row:
            return render_template("key.html", key=row["key_plain"])
        return redirect(url_for("index"))

    mark_session_verified(session_id)
    key = create_key_for_session(session_id, device_fp, session_data["game"], 24)

    session.pop("pending_session", None)

    return render_template("key.html", key=key)


@app.route("/api/validate", methods=["POST"])
def api_validate():
    data = request.get_json()
    key = data.get("key", "")
    device_fp = get_device_fingerprint(request)

    key_hash = hash_key(key)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM keys WHERE key_hash = ?", (key_hash,)).fetchone()

    if not row:
        conn.close()
        return jsonify({"valid": False, "message": "Key khong ton tai."})

    if row["device_fp"] != device_fp:
        conn.close()
        return jsonify({"valid": False, "message": "Key da dung tren thiet bi khac."})

    expires = datetime.fromisoformat(row["expires_at"])
    if datetime.utcnow() > expires:
        conn.close()
        return jsonify({"valid": False, "message": "Key da het han."})

    if row["uses"] >= row["max_uses"]:
        conn.close()
        return jsonify({"valid": False, "message": "Key da het so lan su dung."})

    conn.execute("UPDATE keys SET uses = uses + 1 WHERE key_hash = ?", (key_hash,))
    conn.commit()
    conn.close()
    return jsonify({"valid": True, "message": "Key hop le!"})


if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
