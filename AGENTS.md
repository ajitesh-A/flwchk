# FLWCHK — Instagram Non-Followers Detector

## Overview
Web app at `instagram_nonfollowers/` that checks which Instagram accounts you follow don't follow you back. Built with Flask + instagrapi, UI from Stitch (stitch.withgoogle.com).

## Architecture
- `server.py` — Flask app with API endpoints
- `main.py` — Entry point, launches Flask on `0.0.0.0:5000`
- `templates/login.html` — Setup/Login screen (Stitch design)
- `templates/dashboard.html` — Main dashboard (Stitch design)
- `static/script.js` — All frontend API wiring
- `static/img/logo.svg` — FLWCHK logo

## Core modules (unchanged from desktop version)
- `auth.py` — Session management, password login, cookie import, account CRUD
- `fetcher.py` — Paginated follower/following fetching (1–2s delay, 200 users/chunk)
- `analyzer.py` — `find_non_followers()` set difference logic

## Key design decisions
- **Session persistence**: instagrapi `Client` settings saved to `sessions/{sid}.json` after login. On cache miss, loaded from disk. Survives server restarts on paid Render (persistent disk).
- **Cookie upload**: Users can export Instagram cookies from browser and upload the file – bypasses password login and 2FA. Accepts both JSON (EditThisCookie/Get cookies.txt) and Netscape (cookies.txt) formats.
- **Proxy support**: `PROXY_URL` env var sets a proxy on the instagrapi client for residential IP routing.
- **Single user per session**: No account switching (multi-account removed for web).
- **Background fetch**: `POST /api/fetch` spawns a `threading.Thread`; client polls `GET /api/fetch-status` for progress.
- **Rate limiting**: 1 concurrent fetch per session (rejected if already running).
- **All Instagram user-info endpoints are broken**: No way to get total counts upfront — progress shows cumulative ("X fetched") only.

## Deployment (Render)
- `Procfile`: `gunicorn main:app`
- `requirements.txt`: `instagrapi`, `flask`, `gunicorn`
- Required env var: `FLASK_SECRET_KEY` (random string for session signing)
- Optional env var: `PROXY_URL` (residential proxy for bypassing Instagram rate limits/2FA)
- Paid tier required for persistent disk (session files survive restarts)

## API endpoints

| Method | Path | Auth | Body | Returns |
|--------|------|------|------|---------|
| POST | `/api/login` | No | `{username, password}` | `{ok, user_id}` or `{ok: false, requires_2fa: true, temp_id}` |
| POST | `/api/login-2fa` | No | `{temp_id, verification_code}` | `{ok, user_id}` |
| POST | `/api/login-cookie` | No | multipart: `cookies` (file) | `{ok, user_id}` |
| POST | `/api/login-session-file` | No | multipart: `session` (file) | `{ok, user_id}` |
| POST | `/api/logout` | Yes | — | `{ok}` |
| POST | `/api/fetch` | Yes | — | `{ok}` |
| GET | `/api/fetch-status` | Yes | — | `{running, phase, current, error}` |
| GET | `/api/results` | Yes | — | `{ok, username, followers, following, non_followers[]}` |
| POST | `/api/unfollow` | Yes | `{user_id}` | `{ok}` |

## 2FA / Login verification
- If Instagram requires a verification code, `/api/login` returns `requires_2fa: true` + `temp_id`
- The Client instance with challenge state is stored in `_pending_logins` dict keyed by `temp_id`
- Frontend shows a verification code input and calls `/api/login-2fa` with the code
- Pending logins expire after 5 minutes (cleaned up by background thread)

## Routes (HTML)
- `GET /` → Login page
- `GET /dashboard` → Dashboard page

## Instagram API limitations
- `user_followers_v1_chunk` and `user_following_v1_chunk` work for fetching lists
- All user info endpoints (`user_info_v1`, `user_info_by_username_gql`, `user_friendship_v1`, etc.) return broken data — no way to check if accounts are deactivated or get profile pics
- `delay_range` set to `[3, 6]` seconds between pagination chunks
