"""
Campus Help Desk - Flask + SQLite backend.

Run:
    python app.py

Then open:
    http://127.0.0.1:5000
"""

import os
import sqlite3
from functools import wraps

from flask import Flask, g, jsonify, request, session, send_file
from werkzeug.security import check_password_hash, generate_password_hash


# ============================================================
# BASIC CONFIGURATION
# ============================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "helpdesk.db")

CATEGORIES = [
    "Academics",
    "Hostel",
    "Library",
    "Fees & Accounts",
    "IT & Wi-Fi",
    "Canteen",
    "Transport",
    "Other"
]

PRIORITIES = [
    "Low",
    "Medium",
    "High"
]

STATUSES = [
    "Open",
    "In Progress",
    "Resolved",
    "Closed"
]


# ============================================================
# FLASK APP
# ============================================================

app = Flask(__name__)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "development-secret-change-this"
)

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=(
        os.environ.get("COOKIE_SECURE", "0") == "1"
    ),
)


# ============================================================
# FRONTEND FILES
# ============================================================

@app.route("/")
def home():
    return send_file(
        os.path.join(BASE_DIR, "index.html")
    )


@app.route("/style.css")
def style():
    return send_file(
        os.path.join(BASE_DIR, "style.css"),
        mimetype="text/css"
    )


@app.route("/app.js")
def javascript():
    return send_file(
        os.path.join(BASE_DIR, "app.js"),
        mimetype="application/javascript"
    )


# ============================================================
# DATABASE SCHEMA
# ============================================================

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'student'
        CHECK (role IN ('student', 'admin')),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS tickets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    title TEXT NOT NULL,
    category TEXT NOT NULL,
    description TEXT NOT NULL,
    priority TEXT NOT NULL DEFAULT 'Medium',
    status TEXT NOT NULL DEFAULT 'Open',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS replies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id INTEGER NOT NULL
        REFERENCES tickets(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id),
    message TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_tickets_user
ON tickets(user_id);

CREATE INDEX IF NOT EXISTS idx_tickets_status
ON tickets(status);

CREATE INDEX IF NOT EXISTS idx_replies_ticket
ON replies(ticket_id);
"""


# ============================================================
# DATABASE
# ============================================================

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")

    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)

    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(DB_PATH)

    db.executescript(SCHEMA)

    admin_exists = db.execute(
        "SELECT 1 FROM users WHERE role = 'admin'"
    ).fetchone()

    if not admin_exists:
        db.execute(
            """
            INSERT INTO users
            (name, email, password_hash, role)
            VALUES (?, ?, ?, 'admin')
            """,
            (
                "Help Desk Admin",
                "admin@college.edu",
                generate_password_hash("admin123")
            )
        )

    db.commit()
    db.close()


# ============================================================
# AUTHENTICATION HELPERS
# ============================================================

def login_required(fn):

    @wraps(fn)
    def wrapper(*args, **kwargs):

        if "user_id" not in session:
            return jsonify(
                error="Log in to continue."
            ), 401

        return fn(*args, **kwargs)

    return wrapper


def admin_required(fn):

    @wraps(fn)
    def wrapper(*args, **kwargs):

        if session.get("role") != "admin":
            return jsonify(
                error="Only help desk staff can do this."
            ), 403

        return fn(*args, **kwargs)

    return login_required(wrapper)


def is_admin():
    return session.get("role") == "admin"


def current_user():

    uid = session.get("user_id")

    if not uid:
        return None

    row = get_db().execute(
        """
        SELECT id, name, email, role
        FROM users
        WHERE id = ?
        """,
        (uid,)
    ).fetchone()

    if row is None:
        session.clear()
        return None

    return dict(row)


def start_session(user_id, role):

    session.clear()

    session["user_id"] = user_id
    session["role"] = role


def fetch_ticket(ticket_id):

    row = get_db().execute(
        """
        SELECT
            t.*,
            u.name AS student_name
        FROM tickets t
        JOIN users u
            ON u.id = t.user_id
        WHERE t.id = ?
        """,
        (ticket_id,)
    ).fetchone()

    if row is None:
        return None

    if not is_admin() and row["user_id"] != session["user_id"]:
        return None

    return row


def body():
    return request.get_json(silent=True) or {}


# ============================================================
# METADATA
# ============================================================

@app.get("/api/meta")
def meta():

    return jsonify(
        categories=CATEGORIES,
        priorities=PRIORITIES,
        statuses=STATUSES
    )


# ============================================================
# ACCOUNT - REGISTER
# ============================================================

@app.post("/api/register")
def register():

    d = body()

    name = (d.get("name") or "").strip()
    email = (d.get("email") or "").strip().lower()
    password = d.get("password") or ""

    if not name or "@" not in email or len(password) < 6:

        return jsonify(
            error=(
                "Enter your name, a valid email and "
                "a password of at least 6 characters."
            )
        ), 400

    db = get_db()

    try:

        cur = db.execute(
            """
            INSERT INTO users
            (name, email, password_hash)
            VALUES (?, ?, ?)
            """,
            (
                name,
                email,
                generate_password_hash(password)
            )
        )

        db.commit()

    except sqlite3.IntegrityError:

        return jsonify(
            error=(
                "An account with this email already exists. "
                "Log in instead."
            )
        ), 409

    start_session(
        cur.lastrowid,
        "student"
    )

    return jsonify(
        user=current_user()
    ), 201


# ============================================================
# ACCOUNT - LOGIN
# ============================================================

@app.post("/api/login")
def login():

    d = body()

    email = (d.get("email") or "").strip().lower()

    row = get_db().execute(
        """
        SELECT *
        FROM users
        WHERE email = ?
        """,
        (email,)
    ).fetchone()

    if (
        row is None
        or not check_password_hash(
            row["password_hash"],
            d.get("password") or ""
        )
    ):

        return jsonify(
            error="Email or password is incorrect."
        ), 401

    start_session(
        row["id"],
        row["role"]
    )

    return jsonify(
        user=current_user()
    )


# ============================================================
# ACCOUNT - LOGOUT
# ============================================================

@app.post("/api/logout")
def logout():

    session.clear()

    return jsonify(
        ok=True
    )


# ============================================================
# ACCOUNT - CURRENT USER
# ============================================================

@app.get("/api/me")
def me():

    return jsonify(
        user=current_user()
    )


# ============================================================
# ACCOUNT - CHANGE PASSWORD
# ============================================================

@app.post("/api/change-password")
@login_required
def change_password():

    d = body()

    email = (d.get("email") or "").strip().lower()

    old_password = d.get("old_password") or ""
    new_password = d.get("new_password") or ""

    row = get_db().execute(
        """
        SELECT *
        FROM users
        WHERE id = ?
        """,
        (session["user_id"],)
    ).fetchone()

    if email != row["email"].lower():

        return jsonify(
            error="That email doesn't match your account."
        ), 400

    if not check_password_hash(
        row["password_hash"],
        old_password
    ):

        return jsonify(
            error="Your current password is incorrect."
        ), 401

    if len(new_password) < 6:

        return jsonify(
            error="New password must be at least 6 characters."
        ), 400

    db = get_db()

    db.execute(
        """
        UPDATE users
        SET password_hash = ?
        WHERE id = ?
        """,
        (
            generate_password_hash(new_password),
            row["id"]
        )
    )

    db.commit()

    return jsonify(
        ok=True
    )


# ============================================================
# STAFF ACCOUNT
# ============================================================

@app.post("/api/staff")
@admin_required
def create_staff():

    d = body()

    name = (d.get("name") or "").strip()
    email = (d.get("email") or "").strip().lower()
    password = d.get("password") or ""

    if not name or "@" not in email or len(password) < 6:

        return jsonify(
            error=(
                "Enter a name, a valid email and "
                "a password of at least 6 characters."
            )
        ), 400

    db = get_db()

    try:

        db.execute(
            """
            INSERT INTO users
            (name, email, password_hash, role)
            VALUES (?, ?, ?, 'admin')
            """,
            (
                name,
                email,
                generate_password_hash(password)
            )
        )

        db.commit()

    except sqlite3.IntegrityError:

        return jsonify(
            error="An account with this email already exists."
        ), 409

    return jsonify(
        ok=True
    ), 201


# ============================================================
# TICKETS - LIST
# ============================================================

@app.get("/api/tickets")
@login_required
def list_tickets():

    where = []
    args = []

    if not is_admin():

        where.append(
            "t.user_id = ?"
        )

        args.append(
            session["user_id"]
        )

    status = request.args.get("status")

    if status in STATUSES:

        where.append(
            "t.status = ?"
        )

        args.append(
            status
        )

    q = (
        request.args.get("q") or ""
    ).strip()

    if q:

        where.append(
            "(t.title LIKE ? OR t.description LIKE ?)"
        )

        args += [
            f"%{q}%",
            f"%{q}%"
        ]

    sql = """
        SELECT
            t.*,
            u.name AS student_name
        FROM tickets t
        JOIN users u
            ON u.id = t.user_id
    """

    if where:

        sql += " WHERE " + " AND ".join(where)

    sql += """
        ORDER BY
            t.updated_at DESC,
            t.id DESC
    """

    rows = get_db().execute(
        sql,
        args
    ).fetchall()

    return jsonify(
        tickets=[
            dict(r)
            for r in rows
        ]
    )


# ============================================================
# TICKETS - CREATE
# ============================================================

@app.post("/api/tickets")
@login_required
def create_ticket():

    d = body()

    title = (d.get("title") or "").strip()

    description = (
        d.get("description") or ""
    ).strip()

    category = d.get("category")

    priority = (
        d.get("priority")
        or "Medium"
    )

    if not title or len(title) > 120:

        return jsonify(
            error="Add a title of up to 120 characters."
        ), 400

    if not description or len(description) > 2000:

        return jsonify(
            error="Describe the problem in up to 2000 characters."
        ), 400

    if (
        category not in CATEGORIES
        or priority not in PRIORITIES
    ):

        return jsonify(
            error="Choose a valid category and priority."
        ), 400

    db = get_db()

    cur = db.execute(
        """
        INSERT INTO tickets
        (
            user_id,
            title,
            category,
            description,
            priority
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            session["user_id"],
            title,
            category,
            description,
            priority
        )
    )

    db.commit()

    return jsonify(
        id=cur.lastrowid
    ), 201


# ============================================================
# TICKETS - VIEW
# ============================================================

@app.get("/api/tickets/<int:ticket_id>")
@login_required
def get_ticket(ticket_id):

    ticket = fetch_ticket(ticket_id)

    if ticket is None:

        return jsonify(
            error="Complaint not found."
        ), 404

    replies = get_db().execute(
        """
        SELECT
            r.id,
            r.message,
            r.created_at,
            u.name,
            u.role
        FROM replies r
        JOIN users u
            ON u.id = r.user_id
        WHERE r.ticket_id = ?
        ORDER BY r.id
        """,
        (ticket_id,)
    ).fetchall()

    return jsonify(
        ticket=dict(ticket),
        replies=[
            dict(r)
            for r in replies
        ]
    )


# ============================================================
# TICKETS - UPDATE STATUS
# ============================================================

@app.patch("/api/tickets/<int:ticket_id>")
@admin_required
def update_ticket(ticket_id):

    status = body().get("status")

    if status not in STATUSES:

        return jsonify(
            error="Choose a valid status."
        ), 400

    if fetch_ticket(ticket_id) is None:

        return jsonify(
            error="Complaint not found."
        ), 404

    db = get_db()

    db.execute(
        """
        UPDATE tickets
        SET
            status = ?,
            updated_at = datetime('now')
        WHERE id = ?
        """,
        (
            status,
            ticket_id
        )
    )

    db.commit()

    return jsonify(
        ok=True
    )


# ============================================================
# REPLIES
# ============================================================

@app.post("/api/tickets/<int:ticket_id>/replies")
@login_required
def add_reply(ticket_id):

    ticket = fetch_ticket(ticket_id)

    if ticket is None:

        return jsonify(
            error="Complaint not found."
        ), 404

    message = (
        body().get("message") or ""
    ).strip()

    if not message or len(message) > 2000:

        return jsonify(
            error="Write a reply of up to 2000 characters."
        ), 400

    if (
        ticket["status"] == "Closed"
        and not is_admin()
    ):

        return jsonify(
            error=(
                "This complaint is closed. "
                "File a new complaint if the problem returns."
            )
        ), 400

    db = get_db()

    db.execute(
        """
        INSERT INTO replies
        (
            ticket_id,
            user_id,
            message
        )
        VALUES (?, ?, ?)
        """,
        (
            ticket_id,
            session["user_id"],
            message
        )
    )

    new_status = (
        "In Progress"
        if is_admin()
        and ticket["status"] == "Open"
        else ticket["status"]
    )

    db.execute(
        """
        UPDATE tickets
        SET
            status = ?,
            updated_at = datetime('now')
        WHERE id = ?
        """,
        (
            new_status,
            ticket_id
        )
    )

    db.commit()

    return jsonify(
        ok=True
    ), 201


# ============================================================
# ADMIN STATISTICS
# ============================================================

@app.get("/api/stats")
@admin_required
def stats():

    rows = get_db().execute(
        """
        SELECT
            status,
            COUNT(*) AS n
        FROM tickets
        GROUP BY status
        """
    ).fetchall()

    counts = {
        s: 0
        for s in STATUSES
    }

    counts.update({
        r["status"]: r["n"]
        for r in rows
    })

    return jsonify(
        counts=counts,
        total=sum(counts.values())
    )


# ============================================================
# INITIALIZE DATABASE
# ============================================================

init_db()


# ============================================================
# RUN APPLICATION
# ============================================================

if __name__ == "__main__":
    app.run(debug=True)
