# FLWCHK — Instagram Non-Followers Detector

## Overview
Web app at `instagram_nonfollowers/` that checks which Instagram accounts you follow don't follow you back. Built with Flask + instagrapi, UI from Stitch (stitch.withgoogle.com).

## Architecture
- `server.py` — Flask app with API endpoints (`/api/login`, `/api/fetch`, `/api/fetch-status`, `/api/results`, `/api/unfollow`, `/api/logout`)
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
- **In-memory sessions**: Each browser gets a Flask signed session cookie; instagrapi `Client` stored in server RAM keyed by session ID. No passwords/accounts written to disk.
- **Single user per session**: No account switching (multi-account removed for web).
- **Background fetch**: `POST /api/fetch` spawns a `threading.Thread`; client polls `GET /api/fetch-status` for progress.
- **Rate limiting**: 1 concurrent fetch per session (rejected if already running).
- **All Instagram user-info endpoints are broken**: No way to get total counts upfront — progress shows cumulative ("X fetched") only.

## Deployment (Render)
- `Procfile`: `gunicorn main:app`
- `requirements.txt`: `instagrapi`, `flask`, `gunicorn`
- Set `FLASK_SECRET_KEY` env var in Render dashboard for production session signing.

## API endpoints

| Method | Path | Auth | Body | Returns |
|--------|------|------|------|---------|
| POST | `/api/login` | No | `{username, password}` | `{ok, user_id}` |
| POST | `/api/logout` | Yes | — | `{ok}` |
| POST | `/api/fetch` | Yes | — | `{ok}` |
| GET | `/api/fetch-status` | Yes | — | `{running, phase, current, error}` |
| GET | `/api/results` | Yes | — | `{ok, username, followers, following, non_followers[]}` |
| POST | `/api/unfollow` | Yes | `{user_id}` | `{ok}` |

## Routes (HTML)
- `GET /` → Login page
- `GET /dashboard` → Dashboard page

## Instagram API limitations
- `user_followers_v1_chunk` and `user_following_v1_chunk` work for fetching lists
- All user info endpoints (`user_info_v1`, `user_info_by_username_gql`, `user_friendship_v1`, etc.) return broken data — no way to check if accounts are deactivated or get profile pics
- `delay_range` set to `[3, 6]` seconds between pagination chunks
