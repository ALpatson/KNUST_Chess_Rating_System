
# KNUST Chess Rating System

This repository is a small Django application used by the KNUST Chess Club to
manage players, enter matches, compute ratings, view rankings, and export
rankings to PDF. A lightweight passcode gate was added to restrict access
to the site for simple deployments.

Contents
 - `chess_club/` — Django project settings and URL configuration
 - `ratings/` — Django app containing models, views, templates and middleware
 - `db.sqlite3` — example SQLite database (development)
 - `requirements.txt` — minimal Python dependencies

Quick overview
 - Player management (add players)
 - Match entry (result entry updates ratings)
 - Ranking page with download-to-PDF feature (ReportLab)
 - Simple site-wide passcode protection with 60-minute expiry

Getting started (development)
1. Create a virtualenv and activate it:

```bash
python -m venv .venv
# Windows
.venv\\Scripts\\activate
# macOS / Linux
source .venv/bin/activate
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Apply migrations and run the server:

```bash
python manage.py migrate
python manage.py runserver
```

4. Open the site at http://127.0.0.1:8000/. The app redirects to a passcode
	 entry page on first visit.

Passcode protection (how it works)
--------------------------------
This project includes a minimal passcode gate intended for lightweight
internal protection — it is not a substitute for Django authentication.

Implementation details
 - Middleware: `ratings.middleware.PasscodeMiddleware` enforces access.
 - View: `ratings.views.PasscodeView` renders `ratings/passcode.html` and
	 verifies submitted passcode.
 - Settings: The passcode is read from the `PASSCODE` environment variable
	 (see below). After successful entry the
	 session keys `access_granted` and `access_granted_at` are stored.
 - Expiry: The middleware checks `access_granted_at` and requires reentry
	 after 60 minutes. To change the timeout update the check in
	 `ratings/middleware.py`.

Passcode
 - The passcode is read from the `PASSCODE` environment variable. When running
   locally with `DEBUG` on and no `PASSCODE` set, it falls back to
   `local-dev-passcode`.

Deployment (Vercel + Supabase)
------------------------------
`vercel.json` routes every request to `api/index.py`, which serves the Django
app. Static files are served by WhiteNoise. Set these environment variables in
Vercel:

| Variable | Value |
| --- | --- |
| `DEBUG` | `False` |
| `SECRET_KEY` | a long random string |
| `PASSCODE` | the club passcode |
| `DATABASE_URL` | Supabase "Transaction pooler" connection string (port 6543) |
| `ALLOWED_HOSTS` | optional, comma-separated custom domains (`*.vercel.app` is always allowed) |

Run migrations against Supabase from your machine with `DATABASE_URL` set:
`python manage.py migrate`.

PDF export
----------
- The ranking page provides a "Download PDF Rankings" button (`players/ranking/pdf/`).
- PDF generation is implemented in `ratings/views.py` (`PlayerRankingPDFView`) using ReportLab.

Files added/modified for passcode & PDF
-------------------------------------
- `ratings/middleware.py` — passcode middleware
- `ratings/views.py` — `PasscodeView`, `PlayerRankingPDFView`
- `ratings/templates/ratings/passcode.html` — passcode entry template
- `ratings/templates/ratings/player_ranking.html` — ranking page (styling + download button)
- `chess_club/settings.py` — `PASSCODE` setting and middleware ordering
- `ratings/urls.py` — `passcode/` and `players/ranking/pdf/` routes

Security notes
--------------
- This passcode gate is intentionally simple. For production use:
	- Use HTTPS.
	- Store secrets in environment variables or a secrets manager.
	- Consider using Django's auth system for per-user accounts and permissions.
	- Harden session cookies (secure, httpOnly) and configure timeouts.

Common troubleshooting
----------------------
- AttributeError: `'WSGIRequest' object has no attribute 'session'`
	- Ensure `django.contrib.sessions.middleware.SessionMiddleware` is before
		`ratings.middleware.PasscodeMiddleware` in `MIDDLEWARE` in `chess_club/settings.py` (the repo already sets this ordering).


