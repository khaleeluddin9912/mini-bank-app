"""
Mini Bank — demo banking app backend.

Real REST API + SQLite storage (swap for Oracle Autonomous DB later —
see README.md "Moving to OCI" section for what changes).

Run:
    pip install -r requirements.txt
    python3 app.py
Then open http://localhost:5000
"""

import sqlite3
import secrets
import datetime
import os
from pathlib import Path

from flask import Flask, request, jsonify, g, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "mini_bank.db"
STATIC_DIR = BASE_DIR / "static"

app = Flask(__name__, static_folder=str(STATIC_DIR), static_url_path="")

# In-memory session store: token -> user_id.
# For production this becomes Redis or DB-backed sessions / real JWT.
SESSIONS = {}

MONTHLY_BUDGET = 60000.00


# ---------------------------------------------------------------------------
# Database setup
# ---------------------------------------------------------------------------

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    fresh = not DB_PATH.exists()
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            account_type TEXT NOT NULL,
            number_masked TEXT NOT NULL,
            balance REAL NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS cards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER NOT NULL REFERENCES accounts(id),
            number_masked TEXT NOT NULL,
            holder_name TEXT NOT NULL,
            expiry TEXT NOT NULL,
            daily_limit REAL NOT NULL DEFAULT 50000,
            frozen INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER NOT NULL REFERENCES accounts(id),
            counterparty TEXT NOT NULL,
            amount REAL NOT NULL,
            direction TEXT NOT NULL CHECK (direction IN ('debit','credit')),
            note TEXT,
            created_at TEXT NOT NULL
        );
        """
    )
    conn.commit()

    if fresh:
        seed(conn)

    conn.close()


def seed(conn):
    pw = generate_password_hash("password123")
    cur = conn.execute(
        "INSERT INTO users (name, email, password_hash) VALUES (?,?,?)",
        ("Asha Rao", "asha@example.com", pw),
    )
    user_id = cur.lastrowid

    cur = conn.execute(
        "INSERT INTO accounts (user_id, account_type, number_masked, balance) VALUES (?,?,?,?)",
        (user_id, "Savings", "•••• 4471", 184320.50),
    )
    account_id = cur.lastrowid

    conn.execute(
        "INSERT INTO cards (account_id, number_masked, holder_name, expiry) VALUES (?,?,?,?)",
        (account_id, "•••• •••• •••• 4471", "Asha Rao", "09/29"),
    )

    now = datetime.datetime.now()
    seed_tx = [
        ("Rent — Kavya PG", 18000.00, "debit", "", now - datetime.timedelta(hours=3)),
        ("Salary credit", 92500.00, "credit", "", now - datetime.timedelta(days=1)),
        ("Electricity board", 2140.00, "debit", "", now - datetime.timedelta(days=5)),
        ("Grocery store", 3260.00, "debit", "", now - datetime.timedelta(days=6)),
        ("Interest credit", 412.30, "credit", "", now - datetime.timedelta(days=10)),
    ]
    for counterparty, amount, direction, note, ts in seed_tx:
        conn.execute(
            "INSERT INTO transactions (account_id, counterparty, amount, direction, note, created_at) "
            "VALUES (?,?,?,?,?,?)",
            (account_id, counterparty, amount, direction, note, ts.isoformat()),
        )
    conn.commit()


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def current_user():
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    token = auth.split(" ", 1)[1]
    return SESSIONS.get(token)


def require_auth():
    user_id = current_user()
    if user_id is None:
        return None, (jsonify({"error": "not authenticated"}), 401)
    return user_id, None


# ---------------------------------------------------------------------------
# Routes — auth
# ---------------------------------------------------------------------------

@app.post("/api/login")
def login():
    data = request.get_json(force=True) or {}
    email = data.get("email", "").strip().lower()
    password = data.get("password", "")

    db = get_db()
    row = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    if row is None or not check_password_hash(row["password_hash"], password):
        return jsonify({"error": "invalid email or password"}), 401

    token = secrets.token_hex(24)
    SESSIONS[token] = row["id"]
    return jsonify({"token": token, "name": row["name"], "email": row["email"]})


@app.post("/api/logout")
def logout():
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        SESSIONS.pop(auth.split(" ", 1)[1], None)
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Routes — accounts / dashboard
# ---------------------------------------------------------------------------

@app.get("/api/me")
def me():
    user_id, err = require_auth()
    if err:
        return err
    db = get_db()
    row = db.execute("SELECT id, name, email FROM users WHERE id = ?", (user_id,)).fetchone()
    return jsonify(dict(row))


@app.get("/api/accounts")
def accounts():
    user_id, err = require_auth()
    if err:
        return err
    db = get_db()
    rows = db.execute(
        "SELECT id, account_type, number_masked, balance FROM accounts WHERE user_id = ?",
        (user_id,),
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.get("/api/transactions")
def transactions():
    user_id, err = require_auth()
    if err:
        return err
    db = get_db()
    account = db.execute("SELECT id FROM accounts WHERE user_id = ? LIMIT 1", (user_id,)).fetchone()
    if account is None:
        return jsonify([])
    rows = db.execute(
        "SELECT * FROM transactions WHERE account_id = ? ORDER BY created_at DESC",
        (account["id"],),
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.get("/api/insights")
def insights():
    user_id, err = require_auth()
    if err:
        return err
    db = get_db()
    account = db.execute("SELECT id FROM accounts WHERE user_id = ? LIMIT 1", (user_id,)).fetchone()
    if account is None:
        return jsonify({"spent": 0, "budget": MONTHLY_BUDGET})

    month_start = datetime.date.today().replace(day=1).isoformat()
    row = db.execute(
        "SELECT COALESCE(SUM(amount),0) AS spent FROM transactions "
        "WHERE account_id = ? AND direction = 'debit' AND created_at >= ?",
        (account["id"], month_start),
    ).fetchone()
    return jsonify({"spent": row["spent"], "budget": MONTHLY_BUDGET})


# ---------------------------------------------------------------------------
# Routes — transfer
# ---------------------------------------------------------------------------

@app.post("/api/transfer")
def transfer():
    user_id, err = require_auth()
    if err:
        return err

    data = request.get_json(force=True) or {}
    to_name = (data.get("to_name") or "").strip()
    to_account = (data.get("to_account") or "").strip()
    note = (data.get("note") or "").strip()
    try:
        amount = float(data.get("amount", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "invalid amount"}), 400

    if not to_name:
        return jsonify({"error": "recipient name is required"}), 400
    if amount <= 0:
        return jsonify({"error": "amount must be greater than zero"}), 400

    db = get_db()
    account = db.execute("SELECT * FROM accounts WHERE user_id = ? LIMIT 1", (user_id,)).fetchone()
    if account is None:
        return jsonify({"error": "no account found"}), 404
    if amount > account["balance"]:
        return jsonify({"error": "insufficient balance"}), 400

    new_balance = account["balance"] - amount
    db.execute("UPDATE accounts SET balance = ? WHERE id = ?", (new_balance, account["id"]))

    now = datetime.datetime.now()
    label = f"{to_name} ({to_account})" if to_account else to_name
    cur = db.execute(
        "INSERT INTO transactions (account_id, counterparty, amount, direction, note, created_at) "
        "VALUES (?,?,?,?,?,?)",
        (account["id"], label, amount, "debit", note, now.isoformat()),
    )
    db.commit()

    return jsonify(
        {
            "transaction_id": f"MB-{now.year}-{cur.lastrowid:05d}",
            "amount": amount,
            "to_name": to_name,
            "to_account": to_account,
            "new_balance": new_balance,
            "created_at": now.isoformat(),
            "fee": 0,
        }
    )


# ---------------------------------------------------------------------------
# Routes — cards
# ---------------------------------------------------------------------------

@app.get("/api/cards")
def cards():
    user_id, err = require_auth()
    if err:
        return err
    db = get_db()
    rows = db.execute(
        """
        SELECT c.* FROM cards c
        JOIN accounts a ON a.id = c.account_id
        WHERE a.user_id = ?
        """,
        (user_id,),
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.patch("/api/cards/<int:card_id>/freeze")
def toggle_freeze(card_id):
    user_id, err = require_auth()
    if err:
        return err
    db = get_db()
    row = db.execute(
        """
        SELECT c.* FROM cards c
        JOIN accounts a ON a.id = c.account_id
        WHERE c.id = ? AND a.user_id = ?
        """,
        (card_id, user_id),
    ).fetchone()
    if row is None:
        return jsonify({"error": "card not found"}), 404

    new_state = 0 if row["frozen"] else 1
    db.execute("UPDATE cards SET frozen = ? WHERE id = ?", (new_state, card_id))
    db.commit()
    return jsonify({"id": card_id, "frozen": bool(new_state)})


# ---------------------------------------------------------------------------
# Static frontend
# ---------------------------------------------------------------------------

@app.get("/")
def index():
    return send_from_directory(STATIC_DIR, "index.html")


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)
