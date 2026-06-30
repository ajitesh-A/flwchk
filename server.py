import os
import time
import uuid
import threading

from flask import Flask, session, request, jsonify, render_template
from functools import wraps

from instagrapi import Client
from instagrapi.exceptions import LoginRequired, ChallengeRequired

from fetcher import fetch_followers, fetch_following
from analyzer import find_non_followers

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-key-change-in-prod")

_sessions: dict[str, dict] = {}
_pending_logins: dict[str, dict] = {}

def get_user_session() -> dict | None:
    sid = session.get("sid")
    if not sid or sid not in _sessions:
        return None
    return _sessions[sid]

def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not get_user_session():
            return jsonify({"ok": False, "error": "Not logged in"}), 401
        return f(*args, **kwargs)
    return decorated

def _cleanup_pending():
    while True:
        time.sleep(300)
        now = time.time()
        expired = [k for k, v in _pending_logins.items() if now - v["created_at"] > 300]
        for k in expired:
            _pending_logins.pop(k, None)

threading.Thread(target=_cleanup_pending, daemon=True).start()


def _make_client() -> Client:
    client = Client()
    client.delay_range = [3, 6]
    client.set_locale("en_US")
    client.set_country("US")
    return client


@app.route("/")
def index():
    return render_template("login.html")

@app.route("/dashboard")
def dashboard_page():
    return render_template("dashboard.html")


@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json()
    username = data.get("username", "").strip()
    password = data.get("password", "")

    if not username or not password:
        return jsonify({"ok": False, "error": "Username and password required"})

    try:
        client = _make_client()
        client.login(username, password)
    except LoginRequired:
        temp_id = str(uuid.uuid4())
        _pending_logins[temp_id] = {
            "client": client,
            "username": username,
            "password": password,
            "created_at": time.time(),
        }
        return jsonify({
            "ok": False,
            "requires_2fa": True,
            "temp_id": temp_id,
            "error": "Instagram requires a verification code. Check your email or SMS.",
        })
    except ChallengeRequired:
        temp_id = str(uuid.uuid4())
        _pending_logins[temp_id] = {
            "client": client,
            "username": username,
            "password": password,
            "created_at": time.time(),
        }
        return jsonify({
            "ok": False,
            "requires_2fa": True,
            "temp_id": temp_id,
            "error": "Instagram requires a challenge response. Check your email or SMS.",
        })
    except Exception as e:
        return jsonify({"ok": False, "error": f"Login failed: {e}"})

    sid = str(uuid.uuid4())
    session["sid"] = sid
    _sessions[sid] = {
        "client": client,
        "username": username,
        "user_id": client.user_id,
        "non_followers": [],
        "followers_count": 0,
        "following_count": 0,
        "task_status": None,
    }

    return jsonify({"ok": True, "user_id": client.user_id})


@app.route("/api/login-2fa", methods=["POST"])
def api_login_2fa():
    data = request.get_json()
    temp_id = data.get("temp_id", "")
    code = data.get("verification_code", "").strip()

    if not temp_id or not code:
        return jsonify({"ok": False, "error": "temp_id and verification_code required"})

    pending = _pending_logins.pop(temp_id, None)
    if not pending:
        return jsonify({"ok": False, "error": "Verification session expired or invalid. Please login again."})

    client = pending["client"]
    username = pending["username"]
    password = pending["password"]

    try:
        client.login(username, password, verification_code=code)
    except Exception as e:
        return jsonify({"ok": False, "error": f"Verification failed: {e}"})

    sid = str(uuid.uuid4())
    session["sid"] = sid
    _sessions[sid] = {
        "client": client,
        "username": username,
        "user_id": client.user_id,
        "non_followers": [],
        "followers_count": 0,
        "following_count": 0,
        "task_status": None,
    }

    return jsonify({"ok": True, "user_id": client.user_id})

@app.route("/api/logout", methods=["POST"])
def api_logout():
    sid = session.pop("sid", None)
    if sid and sid in _sessions:
        del _sessions[sid]
    return jsonify({"ok": True})

@app.route("/api/fetch", methods=["POST"])
@requires_auth
def api_fetch():
    us = get_user_session()
    if us.get("task_status") and us["task_status"].get("running"):
        return jsonify({"ok": False, "error": "Fetch already in progress"})

    client = us["client"]
    user_id = us["user_id"]
    status = {"phase": "starting", "current": 0, "running": True, "error": None}
    us["task_status"] = status

    def run():
        try:
            status["phase"] = "followers"
            followers = fetch_followers(client, user_id, lambda n: status.update({"current": n}))
            status["phase"] = "following"
            following = fetch_following(client, user_id, lambda n: status.update({"current": n}))
            status["phase"] = "analyzing"
            non_followers = find_non_followers(following, followers)
            us["non_followers"] = non_followers
            us["followers_count"] = len(followers)
            us["following_count"] = len(following)
            status["phase"] = "done"
        except Exception as e:
            status["phase"] = "error"
            status["error"] = str(e)
        finally:
            status["running"] = False

    threading.Thread(target=run, daemon=True).start()
    return jsonify({"ok": True})

@app.route("/api/fetch-status", methods=["GET"])
@requires_auth
def api_fetch_status():
    us = get_user_session()
    status = us.get("task_status", {})
    return jsonify({
        "running": status.get("running", False),
        "phase": status.get("phase", ""),
        "current": status.get("current", 0),
        "error": status.get("error"),
    })

@app.route("/api/results", methods=["GET"])
@requires_auth
def api_results():
    us = get_user_session()
    return jsonify({
        "ok": True,
        "username": us.get("username", ""),
        "followers": us.get("followers_count", 0),
        "following": us.get("following_count", 0),
        "non_followers": us.get("non_followers", []),
    })

@app.route("/api/unfollow", methods=["POST"])
@requires_auth
def api_unfollow():
    us = get_user_session()
    data = request.get_json()
    target_id = int(data["user_id"])
    try:
        us["client"].user_unfollow(target_id)
        us["non_followers"] = [u for u in us["non_followers"] if u["pk"] != target_id]
        if us.get("following_count", 0) > 0:
            us["following_count"] -= 1
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})
