import json
from pathlib import Path
from instagrapi import Client
from instagrapi.exceptions import ClientError

SESSIONS_DIR = Path(__file__).parent / "sessions"
_LAST_ACCOUNT_FILE = SESSIONS_DIR / "last_account.txt"


def save_last_account(account: str):
    SESSIONS_DIR.mkdir(exist_ok=True)
    _LAST_ACCOUNT_FILE.write_text(account, encoding="utf-8")


def get_last_account() -> str | None:
    SESSIONS_DIR.mkdir(exist_ok=True)
    if _LAST_ACCOUNT_FILE.exists():
        return _LAST_ACCOUNT_FILE.read_text(encoding="utf-8").strip()
    return None


def _session_path(account: str) -> Path:
    SESSIONS_DIR.mkdir(exist_ok=True)
    return SESSIONS_DIR / f"{account}.json"


def list_accounts() -> list[str]:
    SESSIONS_DIR.mkdir(exist_ok=True)
    files = sorted(SESSIONS_DIR.glob("*.json"))
    names = []
    for f in files:
        try:
            with open(f, encoding="utf-8") as fh:
                data = json.load(fh)
            name = data.get("account_name", f.stem)
        except Exception:
            name = f.stem
        names.append(name)
    return names


def import_cookies(account: str, cookies_file: str) -> str:
    COOKIE_DOMAIN = ".instagram.com"

    def _parse_cookies_txt(path: str) -> dict:
        cookies = {}
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split("\t")
                if len(parts) < 7:
                    continue
                if COOKIE_DOMAIN not in parts[0]:
                    continue
                key = parts[5]
                value = parts[6]
                cookies[key] = value
        return cookies

    cookies = _parse_cookies_txt(cookies_file)

    required = {"sessionid", "csrftoken", "ds_user_id"}
    missing = required - cookies.keys()
    if missing:
        raise RuntimeError(
            f"Missing required cookies: {', '.join(missing)}"
        )

    client = Client()
    client.set_locale("en_US")
    client.set_country("US")

    settings = client.get_settings()
    settings["cookies"] = cookies
    settings["account_name"] = account

    path = _session_path(account)
    with open(path, "w") as f:
        json.dump(settings, f, indent=4)

    return cookies.get("ds_user_id")


def rename_account(old_name: str, new_name: str):
    old_path = _session_path(old_name)
    new_path = _session_path(new_name)
    if not old_path.exists():
        raise FileNotFoundError(f"Account '{old_name}' not found")
    if new_path.exists():
        raise FileExistsError(f"Account '{new_name}' already exists")

    with open(old_path, encoding="utf-8") as f:
        settings = json.load(f)
    settings["account_name"] = new_name

    old_path.rename(new_path)
    with open(new_path, "w") as f:
        json.dump(settings, f, indent=4)


def delete_account(account: str):
    path = _session_path(account)
    if path.exists():
        path.unlink()


def _make_client() -> Client:
    client = Client()
    client.delay_range = [3, 6]
    client.set_locale("en_US")
    client.set_country("US")
    return client


def save_session(client: Client, account: str):
    settings = client.get_settings()
    settings["account_name"] = account
    path = _session_path(account)
    with open(path, "w") as f:
        json.dump(settings, f, indent=4)


def login_with_password(username: str, password: str) -> Client:
    client = _make_client()
    try:
        client.login(username, password)
    except Exception as e:
        raise RuntimeError(f"Instagram login failed: {e}")
    save_session(client, username)
    return client


def get_client(account: str) -> Client:
    session_file = _session_path(account)

    if not session_file.exists():
        raise RuntimeError(f"Session not found for account '{account}'")

    client = _make_client()

    try:
        client.load_settings(session_file)
        if not client.user_id:
            raise RuntimeError("Invalid session")
        return client
    except Exception as e:
        raise RuntimeError(f"Failed to load session for '{account}': {e}")
