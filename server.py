import os
import json
import time
import uuid
import threading
from pathlib import Path

from flask import Flask, session, request, jsonify, render_template
from functools import wraps

from instagrapi import Client
from instagrapi.exceptions import LoginRequired, ChallengeRequired

from fetcher import fetch_followers, fetch_following
from analyzer import find_non_followers

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-key-change-in-prod")

SESSIONS_DIR = Path(__file__).parent / "sessions"
_sessions: dict[str, dict] = {}
_pending_logins: dict[str, dict] = {}

def _save_session_data(sid: str, us: dict):
    SESSIONS_DIR.mkdir(exist_ok=True)
    settings = us["client"].get_settings()
    settings["_meta"] = {
        "username": us["username"],
        "user_id": us["user_id"],
    }
    with open(SESSIONS_DIR / f"{sid}.json", "w") as f:
        json.dump(settings, f)

def _load_session_data(sid: str) -> dict | None:
    path = SESSIONS_DIR / f"{sid}.json"
    if not path.exists():
        return None
    try:
        with open(path) as f:
            settings = json.load(f)
        meta = settings.pop("_meta", {})
        client = _make_client()
        client.set_settings(settings)
        return {
            "client": client,
            "username": meta.get("username", ""),
            "user_id": meta.get("user_id", client.user_id),
            "non_followers": [],
            "followers_count": 0,
            "following_count": 0,
            "task_status": None,
        }
    except Exception:
        return None

def _delete_session_data(sid: str):
    path = SESSIONS_DIR / f"{sid}.json"
    if path.exists():
        path.unlink()

def get_user_session() -> dict | None:
    sid = session.get("sid")
    if not sid:
        return None
    if sid not in _sessions:
        us = _load_session_data(sid)
        if us:
            _sessions[sid] = us
    return _sessions.get(sid)

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
    proxy = os.environ.get("PROXY_URL")
    if proxy:
        client.set_proxy(proxy)
    return client


@app.route("/")
def index():
    return render_template("login.html")

@app.route("/dashboard")
def dashboard_page():
    return render_template("dashboard.html")


COOKIE_DOMAIN = ".instagram.com"

def _build_client_from_cookies(cookies: dict) -> Client:
    required = {"sessionid", "csrftoken", "ds_user_id"}
    missing = required - cookies.keys()
    if missing:
        raise RuntimeError(f"Missing required cookies: {', '.join(missing)}")
    client = _make_client()
    settings = client.get_settings()
    settings["cookies"] = cookies
    client.set_settings(settings)
    if not client.user_id:
        raise RuntimeError("Could not verify user from cookies")
    return client

def _make_client_from_file(content: str) -> Client:
    try:
        data = json.loads(content)
        if isinstance(data, list):
            cookies = {}
            for c in data:
                if isinstance(c, dict) and c.get("name") and COOKIE_DOMAIN in c.get("domain", ""):
                    cookies[c["name"]] = c["value"]
            return _build_client_from_cookies(cookies)
    except json.JSONDecodeError:
        pass

    cookies = {}
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) >= 7 and COOKIE_DOMAIN in parts[0]:
            cookies[parts[5]] = parts[6]
    return _build_client_from_cookies(cookies)


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
    except LoginRequired as e:
        challenge = getattr(e, "challenge", None)
        if challenge and challenge.get("api_path"):
            challenge_url = f"https://i.instagram.com{challenge['api_path']}"
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
                "challenge_url": challenge_url,
                "error": "Instagram requires a manual challenge. Open the URL in your browser to complete it, then click Verify.",
            })
        return jsonify({
            "ok": False,
            "error": "Instagram rejected this login attempt. Use a residential proxy (PROXY_URL) or upload cookies instead.",
        })
    except ChallengeRequired as e:
        challenge = getattr(e, "challenge", None)
        challenge_url = None
        if challenge and challenge.get("api_path"):
            challenge_url = f"https://i.instagram.com{challenge['api_path']}"
        temp_id = str(uuid.uuid4())
        _pending_logins[temp_id] = {
            "client": client,
            "username": username,
            "password": password,
            "created_at": time.time(),
        }
        resp = {
            "ok": False,
            "requires_2fa": True,
            "temp_id": temp_id,
        }
        if challenge_url:
            resp["challenge_url"] = challenge_url
            resp["error"] = "Instagram requires a manual challenge. Open the URL in your browser to complete it, then click Verify."
        else:
            resp["error"] = "Instagram requires a verification code. Check your email or SMS."
        return jsonify(resp)
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
    _save_session_data(sid, _sessions[sid])

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
    _save_session_data(sid, _sessions[sid])

    return jsonify({"ok": True, "user_id": client.user_id})

@app.route("/api/login-cookie", methods=["POST"])
def api_login_cookie():
    if "cookies" not in request.files:
        return jsonify({"ok": False, "error": "No file uploaded"})
    file = request.files["cookies"]
    if file.filename == "":
        return jsonify({"ok": False, "error": "No file selected"})
    try:
        content = file.read().decode("utf-8")
        client = _make_client_from_file(content)
    except Exception as e:
        return jsonify({"ok": False, "error": f"Failed to parse cookies: {e}"})

    sid = str(uuid.uuid4())
    session["sid"] = sid
    _sessions[sid] = {
        "client": client,
        "username": "user",
        "user_id": client.user_id,
        "non_followers": [],
        "followers_count": 0,
        "following_count": 0,
        "task_status": None,
    }
    _save_session_data(sid, _sessions[sid])
    return jsonify({"ok": True, "user_id": client.user_id})

@app.route("/api/login-session-file", methods=["POST"])
def api_login_session_file():
    if "session" not in request.files:
        return jsonify({"ok": False, "error": "No file uploaded"})
    file = request.files["session"]
    if file.filename == "":
        return jsonify({"ok": False, "error": "No file selected"})
    try:
        content = file.read().decode("utf-8")
        settings = json.loads(content)
        meta = settings.pop("_meta", {})
        client = _make_client()
        client.set_settings(settings)
        if not client.user_id:
            raise RuntimeError("Invalid session file")
    except Exception as e:
        return jsonify({"ok": False, "error": f"Failed to load session: {e}"})

    sid = str(uuid.uuid4())
    session["sid"] = sid
    _sessions[sid] = {
        "client": client,
        "username": meta.get("account_name", meta.get("username", "user")),
        "user_id": client.user_id,
        "non_followers": [],
        "followers_count": 0,
        "following_count": 0,
        "task_status": None,
    }
    _save_session_data(sid, _sessions[sid])
    return jsonify({"ok": True, "user_id": client.user_id})

@app.route("/api/login-sessionid", methods=["POST"])
def api_login_sessionid():
    data = request.get_json()
    sessionid = data.get("sessionid", "").strip()
    if not sessionid:
        return jsonify({"ok": False, "error": "sessionid is required"})

    ds_user_id = data.get("ds_user_id", "").strip()
    csrftoken = data.get("csrftoken", "").strip()

    if not ds_user_id and "%3A" in sessionid:
        ds_user_id = sessionid.split("%3A")[0]
    if not ds_user_id and ":" in sessionid:
        ds_user_id = sessionid.split(":")[0]
    if not ds_user_id:
        return jsonify({"ok": False, "error": "Could not determine user ID from sessionid. Also paste ds_user_id from cookies."})
    if not csrftoken:
        csrftoken = "missing"

    try:
        int(ds_user_id)
    except ValueError:
        return jsonify({"ok": False, "error": f"Invalid user ID: {ds_user_id}"})

    client = _make_client()
    settings = client.get_settings()
    settings["cookies"] = {
        "sessionid": sessionid,
        "csrftoken": csrftoken,
        "ds_user_id": ds_user_id,
    }
    client.set_settings(settings)
    client.user_id = int(ds_user_id)

    try:
        client.get_timeline_feed()
    except Exception:
        pass

    sid = str(uuid.uuid4())
    session["sid"] = sid
    _sessions[sid] = {
        "client": client,
        "username": "",
        "user_id": client.user_id,
        "non_followers": [],
        "followers_count": 0,
        "following_count": 0,
        "task_status": None,
    }
    _save_session_data(sid, _sessions[sid])
    return jsonify({"ok": True, "user_id": client.user_id})

@app.route("/api/logout", methods=["POST"])
def api_logout():
    sid = session.pop("sid", None)
    if sid:
        _sessions.pop(sid, None)
        _delete_session_data(sid)
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
