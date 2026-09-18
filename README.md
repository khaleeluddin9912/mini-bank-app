# Mini Bank — working demo

A real, working banking demo app: Flask + SQLite backend, vanilla JS frontend.
Login, view balance and transactions, transfer money (with real balance
deduction and validation), freeze/unfreeze a card.

## Run it

```bash
cd mini-bank-app
pip install -r requirements.txt
python3 app.py
```

Open http://localhost:5000

**Demo login:** `asha@example.com` / `password123` (pre-filled on the login screen).

The first run creates `mini_bank.db` (SQLite) with seed data: one savings
account, one card, and a handful of transactions. Delete `mini_bank.db` and
restart to reset the demo data.

## What's real here

- Passwords are hashed with Werkzeug's `generate_password_hash` — not stored
  in plaintext.
- Transfers are validated server-side (amount > 0, sufficient balance) and
  actually debit the account and write a transaction row.
- Auth is a bearer token issued on login and required on every account/
  transaction/transfer/card route — unauthenticated requests get a 401.
- All of this was tested end-to-end with `curl` before being handed to you:
  login → check balance → transfer → balance updates → insufficient-balance
  rejection → card freeze toggle → unauthenticated request rejected.

## What's simplified (and what to change for real production use)

- **Sessions are in-memory** (`SESSIONS` dict in `app.py`). Restarting the
  server logs everyone out. Swap for Redis-backed sessions or real JWTs
  before running more than one instance.
- **Single demo user, single account.** There's no signup flow — add one
  before using this for more than a demo.
- **No rate limiting / CSRF protection** — add before exposing publicly.
- **Flask's built-in dev server** (`app.run(debug=True)`) is not production-
  grade. Run behind Gunicorn/uWSGI in production.

## Moving this onto your OCI architecture

This app maps directly onto the architecture you designed:

| This demo | On OCI |
|---|---|
| SQLite (`mini_bank.db`) | Autonomous DB — swap `sqlite3` calls for `oracledb` (python-oracledb), same SQL mostly works |
| Flask dev server | Gunicorn behind the app tier instance pool, private subnet |
| Static files served by Flask | Move to the web tier, or keep served by Flask if you want one simpler tier |
| In-memory sessions | Move to a small Redis instance, or issue real JWTs so any app instance can validate a token without shared memory |
| Hardcoded demo login | Real signup + hashed passwords already in place — just add a `/api/signup` route |
| No secrets file | Put `SECRET_KEY` / DB credentials in OCI Vault, read at startup via env vars |

Suggested next step: containerize this (`Dockerfile` with Gunicorn), push to
OCI Container Registry, run it on the app-tier instance pool behind your
internal load balancer, and point `DB_PATH`/connection string at Autonomous DB
instead of SQLite.

## Project structure

```
mini-bank-app/
├── app.py              Flask backend + all API routes
├── requirements.txt
├── README.md
└── static/
    ├── index.html       All 5 screens (login, home, cards, transfer, success)
    ├── style.css
    └── app.js           Fetch calls to the API, screen navigation, rendering
```
