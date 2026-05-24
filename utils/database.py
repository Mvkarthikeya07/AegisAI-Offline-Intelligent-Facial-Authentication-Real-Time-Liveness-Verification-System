import sqlite3
import time
import threading
from datetime import date, datetime
from werkzeug.security import check_password_hash, generate_password_hash

DB_PATH = "database.db"
WRITE_LOCK = threading.RLock()


def get_connection():
    conn = sqlite3.connect(DB_PATH, timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=10000;")
    return conn


def with_db_retry(action, retries=8, delay=0.25):
    for attempt in range(retries):
        try:
            with WRITE_LOCK:
                return action()
        except sqlite3.OperationalError as exc:
            if "database is locked" not in str(exc).lower() or attempt == retries - 1:
                raise
            time.sleep(delay * (attempt + 1))


def init_db():
    def _write():
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL;")
            cur.execute("PRAGMA synchronous=NORMAL;")
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS app_users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL,
                    role TEXT NOT NULL CHECK (role IN ('admin', 'user'))
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS people (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    place TEXT NOT NULL,
                    phone TEXT UNIQUE NOT NULL,
                    embedding_key TEXT UNIQUE NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS attendance (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    person_id INTEGER NOT NULL,
                    date TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'present',
                    last_seen TEXT NOT NULL,
                    UNIQUE(person_id, date),
                    FOREIGN KEY(person_id) REFERENCES people(id)
                )
                """
            )
            conn.commit()
        finally:
            conn.close()

    with_db_retry(_write)


def ensure_default_users():
    def _write():
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "INSERT OR IGNORE INTO app_users (username, password, role) VALUES (?, ?, ?)",
                ("admin", generate_password_hash("admin123"), "admin"),
            )
            cur.execute(
                "INSERT OR IGNORE INTO app_users (username, password, role) VALUES (?, ?, ?)",
                ("user", generate_password_hash("user123"), "user"),
            )
            conn.commit()
        finally:
            conn.close()

    with_db_retry(_write)


def validate_login(username, password, role):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, username, password, role FROM app_users WHERE username=? AND role=?", (username, role))
        row = cur.fetchone()
    finally:
        conn.close()
    if not row:
        return None
    raw = dict(row)
    stored_password = raw["password"]
    # Backward compatibility for older plaintext rows.
    if stored_password == password or check_password_hash(stored_password, password):
        return {"id": raw["id"], "username": raw["username"], "role": raw["role"]}
    return None


def create_app_user(username, password, role):
    def _write():
        now_hash = generate_password_hash(password)
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO app_users (username, password, role) VALUES (?, ?, ?)",
                (username, now_hash, role),
            )
            conn.commit()
        finally:
            conn.close()

    with_db_retry(_write)


def update_app_user_password(username, role, new_password):
    def _write():
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "UPDATE app_users SET password=? WHERE username=? AND role=?",
            (generate_password_hash(new_password), username, role),
        )
        changed = cur.rowcount
        conn.commit()
        conn.close()
        return changed > 0

    return with_db_retry(_write)


def create_person(name, place, phone, embedding_key):
    def _write():
        now = datetime.now().isoformat(timespec="seconds")
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO people (name, place, phone, embedding_key, created_at) VALUES (?, ?, ?, ?, ?)",
            (name, place, phone, embedding_key, now),
        )
        person_id = cur.lastrowid
        conn.commit()
        cur.execute("SELECT * FROM people WHERE id=?", (person_id,))
        row = cur.fetchone()
        conn.close()
        return dict(row)

    return with_db_retry(_write)


def upsert_person_by_phone(name, place, phone, embedding_key):
    def _write():
        now = datetime.now().isoformat(timespec="seconds")
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT id FROM people WHERE phone=?", (phone,))
            existing = cur.fetchone()
            if existing:
                cur.execute(
                    "UPDATE people SET name=?, place=?, embedding_key=? WHERE phone=?",
                    (name, place, embedding_key, phone),
                )
                person_id = existing["id"]
            else:
                cur.execute(
                    "INSERT INTO people (name, place, phone, embedding_key, created_at) VALUES (?, ?, ?, ?, ?)",
                    (name, place, phone, embedding_key, now),
                )
                person_id = cur.lastrowid
            conn.commit()
            cur.execute("SELECT * FROM people WHERE id=?", (person_id,))
            row = cur.fetchone()
            return dict(row)
        finally:
            conn.close()

    return with_db_retry(_write)


def get_person_by_embedding_key(embedding_key):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM people WHERE embedding_key=?", (embedding_key,))
        row = cur.fetchone()
    finally:
        conn.close()
    return dict(row) if row else None


def mark_present(person_id, seen_at):
    def _write():
        today = date.today().isoformat()
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO attendance (person_id, date, status, last_seen)
            VALUES (?, ?, 'present', ?)
            ON CONFLICT(person_id, date)
            DO UPDATE SET status='present', last_seen=excluded.last_seen
            """,
            (person_id, today, seen_at),
        )
        conn.commit()
        conn.close()

    with_db_retry(_write)


def get_attendance_snapshot(target_date):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT p.name, p.place, p.phone, a.last_seen
            FROM people p
            JOIN attendance a ON a.person_id = p.id
            WHERE a.date = ? AND a.status = 'present'
            ORDER BY p.name
            """,
            (target_date,),
        )
        present = [dict(r) for r in cur.fetchall()]

        cur.execute(
            """
            SELECT p.name, p.place, p.phone
            FROM people p
            LEFT JOIN attendance a ON a.person_id = p.id AND a.date = ?
            WHERE a.person_id IS NULL
            ORDER BY p.name
            """,
            (target_date,),
        )
        absent = [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()

    return {"present": present, "absent": absent}


def list_people():
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, name, place, phone, created_at
            FROM people
            ORDER BY created_at DESC
            """
        )
        rows = [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()
    return rows
