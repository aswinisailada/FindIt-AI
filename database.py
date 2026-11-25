
import hashlib
import hmac
import os
import sqlite3
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "findit.db"


def get_connection():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def hash_password(password, salt=None):
    if salt is None:
        salt = os.urandom(16)
    hashed = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 200000)
    return salt.hex(), hashed.hex()


def verify_password(password, salt_hex, password_hash):
    _, entered_hash = hash_password(password, bytes.fromhex(salt_hex))
    return hmac.compare_digest(entered_hash, password_hash)


def initialize_database():
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                email TEXT NOT NULL UNIQUE,
                password_salt TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_type TEXT NOT NULL,
                item_name TEXT NOT NULL,
                category TEXT,
                color TEXT,
                location TEXT,
                report_date TEXT,
                description TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(reports)").fetchall()
        }
        migrations = {
            "image_path": "TEXT",
            "contact_email": "TEXT",
            "contact_phone": "TEXT",
            "status": "TEXT NOT NULL DEFAULT 'Active'",
            "user_id": "INTEGER REFERENCES users(id)",
            "contact_share_consent": "INTEGER NOT NULL DEFAULT 0",
        }
        for column, definition in migrations.items():
            if column not in columns:
                conn.execute(f"ALTER TABLE reports ADD COLUMN {column} {definition}")
        conn.execute("""
            UPDATE reports SET created_at = CURRENT_TIMESTAMP
            WHERE created_at IS NULL OR TRIM(created_at) = ''
        """)
        conn.execute("""
            UPDATE reports SET status = 'Active'
            WHERE status IS NULL OR TRIM(status) = ''
        """)


def register_user(username, email, password):
    username, email = username.strip(), email.strip().lower()
    if len(username) < 3:
        return False, "Username must contain at least 3 characters."
    if "@" not in email or "." not in email.split("@")[-1]:
        return False, "Please enter a valid email address."
    if len(password) < 8:
        return False, "Password must contain at least 8 characters."
    salt, password_hash = hash_password(password)
    try:
        with get_connection() as conn:
            conn.execute("""
                INSERT INTO users (username, email, password_salt, password_hash)
                VALUES (?, ?, ?, ?)
            """, (username, email, salt, password_hash))
        return True, "Account created successfully. Please log in."
    except sqlite3.IntegrityError:
        return False, "This username or email is already registered."


def authenticate_user(login, password):
    login = login.strip()
    with get_connection() as conn:
        user = conn.execute("""
            SELECT id, username, email, password_salt, password_hash
            FROM users WHERE lower(username) = lower(?) OR lower(email) = lower(?)
        """, (login, login)).fetchone()
    if user is None or not verify_password(password, user["password_salt"], user["password_hash"]):
        return None
    return {"id": int(user["id"]), "username": user["username"], "email": user["email"]}


def add_report(user_id, report_type, item_name, category, color, location,
               report_date, description, contact_email="", contact_phone="",
               image_path=None, contact_share_consent=False):
    report_type = report_type.strip().title()
    if report_type not in ("Lost", "Found"):
        raise ValueError("Report type must be Lost or Found.")
    if not item_name.strip() or not location.strip():
        raise ValueError("Item name and location are required.")
    with get_connection() as conn:
        cursor = conn.execute("""
            INSERT INTO reports (
                user_id, report_type, item_name, category, color, location,
                report_date, description, contact_email, contact_phone,
                image_path, contact_share_consent, status, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Active', CURRENT_TIMESTAMP)
        """, (
            int(user_id), report_type, item_name.strip(), category,
            color.strip(), location.strip(), str(report_date),
            description.strip(), contact_email.strip(), contact_phone.strip(),
            image_path, int(bool(contact_share_consent))
        ))
        return cursor.lastrowid


def get_public_reports(report_type=None):
    """Return public fields only; never expose contact details or account IDs."""
    query = """
        SELECT id, report_type, item_name, category, color, location,
               report_date, description, created_at, status, image_path
        FROM reports
    """
    params = ()
    if report_type:
        query += " WHERE report_type = ?"
        params = (report_type,)
    query += " ORDER BY id DESC"
    with get_connection() as conn:
        return pd.read_sql_query(query, conn, params=params)


def get_my_reports(user_id):
    with get_connection() as conn:
        return pd.read_sql_query("""
            SELECT id, report_type, item_name, category, color, location,
                   report_date, description, status, contact_email,
                   contact_phone, image_path
            FROM reports WHERE user_id = ? ORDER BY id DESC
        """, conn, params=(int(user_id),))


def get_finder_contact_for_lost_owner(lost_report_id, found_report_id,
                                      requester_user_id, score):
    # Score is a candidate-ranking signal, not proof of ownership.
    if float(score) < 70:
        return None
    with get_connection() as conn:
        result = conn.execute("""
            SELECT f.contact_email, f.contact_phone, f.item_name
            FROM reports AS l JOIN reports AS f ON f.id = ?
            WHERE l.id = ? AND l.report_type = 'Lost'
              AND f.report_type = 'Found' AND l.user_id = ?
              AND l.user_id IS NOT NULL AND f.user_id IS NOT NULL
              AND f.user_id != l.user_id
              AND f.contact_share_consent = 1
              AND l.status = 'Active' AND f.status = 'Active'
        """, (int(found_report_id), int(lost_report_id), int(requester_user_id))).fetchone()
    if result is None:
        return None
    return {
        "item_name": result["item_name"],
        "contact_email": result["contact_email"] or "",
        "contact_phone": result["contact_phone"] or "",
    }


def update_report_status(report_id, user_id, status):
    if status not in ("Active", "Returned"):
        raise ValueError("Invalid status.")
    with get_connection() as conn:
        cursor = conn.execute("""
            UPDATE reports SET status = ? WHERE id = ? AND user_id = ?
        """, (status, int(report_id), int(user_id)))
        return cursor.rowcount > 0


initialize_database()
