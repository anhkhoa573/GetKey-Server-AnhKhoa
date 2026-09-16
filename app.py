from flask import Flask, render_template, request, jsonify
import hashlib
from database import (
    init_db, create_session, get_session, mark_session_verified,
    create_key, validate_key
)
from bypass import verify_bypass

app = Flask(__name__)
app.secret_key = "change-this-secret-key-in-production"

LINK_MAP = {
    "link4m": "https://link4m.co/your-link-here",
    "gtraffic": "https://gtraffic.net/your-link-here"
}


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
    duration = int(data.get("duration", 12))
    service = data.get("service", "link4m")

    if duration not in [12, 24]:
        return jsonify({"ok": False, "error": "Thoi han khong hop le."})

    if service not in LINK_MAP:
        return jsonify({"ok": False, "error": "Dich vu khong hop le."})

    device_fp = get_device_fingerprint(request)
    session_id = create_session(game, duration, service, device_fp)

    return jsonify({
        "ok": True,
        "session_id": session_id,
        "bypass_url": LINK_MAP[service],
        "service": service
    })


@app.route("/api/verify", methods=["POST"])
def api_verify():
    data = request.get_json()
    session_id = data.get("session_id", "")
    verify_url = data.get("verify_url", "")

    session_data = get_session(session_id)
    if not session_data:
        return jsonify({"ok": False, "error": "Session khong ton tai."})

    if session_data["status"] == "verified":
        return jsonify({"ok": False, "error": "Session da duoc su dung."})

    success, result = verify_bypass(session_data["service"], verify_url)

    if not success:
        return jsonify({"ok": False, "error": result})

    mark_session_verified(session_id)

    device_fp = get_device_fingerprint(request)
    key = create_key(
        session_id,
        device_fp,
        session_data["game"],
        session_data["duration"],
        session_data["service"]
    )

    return jsonify({
        "ok": True,
        "key": key,
        "duration": session_data["duration"],
        "game": session_data["game"],
        "message": "Key co hieu luc " + str(session_data["duration"]) + " gio."
    })


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
