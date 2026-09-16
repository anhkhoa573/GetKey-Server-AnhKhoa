from flask import Flask, render_template, request, jsonify, redirect, url_for, session
import hashlib
import os
from datetime import datetime, timedelta
from functools import wraps
from database import (
    init_db, create_user, authenticate,
    create_session, get_session, mark_session_verified,
    create_key_for_session, check_daily_limit, increment_daily_limit,
    validate_key
)

app = Flask(__name__)
app.secret_key = "anhkhoa-vip-key-2024-secret"
app.permanent_session_lifetime = timedelta(days=7)

LINK4M_URL = "https://link4m.net/ov9vn2T9"
CALLBACK_URL = "https://getkey-server-anhkhoa.onrender.com/callback"


def get_device_fingerprint(req):
    ip = req.remote_addr or "unknown"
    ua = req.headers.get("User-Agent", "")
    return hashlib.sha256((ip + "|" + ua).encode()).hexdigest()[:32]


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        data = request.get_json()
        username = data.get("username", "").strip()
        password = data.get("password", "")
        if data.get("action") == "register":
            ok, msg = create_user(username, password)
            if not ok:
                return jsonify({"ok": False, "error": msg})
            user = authenticate(username, password)
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session.permanent = True
            return jsonify({"ok": True, "message": msg})
        user = authenticate(username, password)
        if not user:
            return jsonify({"ok": False, "error": "Sai ten dang nhap hoac mat khau."})
        session["user_id"] = user["id"]
        session["username"] = user["username"]
        session.permanent = True
        return jsonify({"ok": True, "message": "Dang nhap thanh cong!"})
    if "user_id" in session:
        return redirect(url_for("index"))
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@login_required
def index():
    user_id = session["user_id"]
    can_use, used, remaining = check_daily_limit(user_id)
    return render_template("index.html", username=session.get("username"),
                           used=used, remaining=remaining, can_use=can_use)


@app.route("/duration")
@login_required
def duration_page():
    return render_template("duration.html")


@app.route("/api/start", methods=["POST"])
@login_required
def api_start():
    user_id = session["user_id"]
    can_use, used, remaining = check_daily_limit(user_id)
    if not can_use:
        return jsonify({"ok": False, "error": "Ban da het 5 luot hom nay. Quay lai vao ngay mai!"})
    data = request.get_json()
    game = data.get("game", "freefire")
    duration = int(data.get("duration", 24))
    if duration not in [12, 24]:
        return jsonify({"ok": False, "error": "Thoi han khong hop le."})
    device_fp = get_device_fingerprint(request)
    session_id = create_session(user_id, game, duration, device_fp)
    session["pending_session"] = session_id
    return jsonify({"ok": True, "session_id": session_id, "bypass_url": LINK4M_URL})


@app.route("/callback")
def callback():
    if "user_id" not in session:
        return redirect(url_for("login"))
    user_id = session["user_id"]
    device_fp = get_device_fingerprint(request)
    session_id = session.get("pending_session", "")
    if not session_id:
        session_id = request.args.get("session", "")
    if not session_id:
        return redirect(url_for("index"))
    session_data = get_session(session_id)
    if not session_data:
        return redirect(url_for("index"))
    if session_data["status"] == "verified":
        return render_template("key.html", key="Ban da lay key roi. Quay lai trang chu.")
    can_use, used, remaining = check_daily_limit(user_id)
    if not can_use:
        return render_template("key.html", key="Het luot hom nay. Quay lai ngay mai.")
    mark_session_verified(session_id)
    increment_daily_limit(user_id)
    key = create_key_for_session(session_id, user_id, device_fp,
                                  session_data["game"], session_data["duration"])
    session.pop("pending_session", None)
    return render_template("key.html", key=key)


@app.route("/api/validate", methods=["POST"])
def api_validate():
    data = request.get_json()
    key = data.get("key", "")
    device_fp = get_device_fingerprint(request)
    valid, message = validate_key(key, device_fp)
    return jsonify({"valid": valid, "message": message})


if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
