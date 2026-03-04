"""
SQLite persistence — periods, hours, accrual snapshot, duplicate hash protection.
"""
import json
import sqlite3
from pathlib import Path
from typing import Any

DB_PATH = Path(__file__).parent.parent / "data" / "payroll.db"


def get_connection():
    """Get SQLite connection with row factory."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create tables if they don't exist."""
    conn = get_connection()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS periods (
                id TEXT PRIMARY KEY,
                start_date TEXT NOT NULL,
                end_date TEXT NOT NULL,
                accrual_snapshot_json TEXT,
                tcp_file_hashes_json TEXT DEFAULT '[]'
            );
            CREATE TABLE IF NOT EXISTS hours (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                period_id TEXT NOT NULL,
                emp_id TEXT NOT NULL,
                date TEXT NOT NULL,
                hrs REAL NOT NULL,
                code TEXT NOT NULL,
                FOREIGN KEY (period_id) REFERENCES periods(id)
            );
            CREATE INDEX IF NOT EXISTS idx_hours_period_emp ON hours(period_id, emp_id);
        """)
        conn.commit()
    finally:
        conn.close()


def create_period(period_id: str, start_date: str, end_date: str, accrual_json: str) -> bool:
    """Create new period. Returns True if created."""
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO periods (id, start_date, end_date, accrual_snapshot_json, tcp_file_hashes_json) VALUES (?, ?, ?, ?, '[]')",
            (period_id, start_date, end_date, accrual_json),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def get_period(period_id: str) -> dict | None:
    """Get period by ID."""
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM periods WHERE id = ?", (period_id,)).fetchone()
        if row is None:
            return None
        return dict(row)
    finally:
        conn.close()


def list_period_ids() -> list[str]:
    """List all period IDs for append mode dropdown."""
    conn = get_connection()
    try:
        rows = conn.execute("SELECT id FROM periods ORDER BY id DESC").fetchall()
        return [r["id"] for r in rows]
    finally:
        conn.close()


def get_tcp_hashes(period_id: str) -> list[str]:
    """Get stored TCP file hashes for duplicate protection."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT tcp_file_hashes_json FROM periods WHERE id = ?", (period_id,)
        ).fetchone()
        if row is None:
            return []
        return json.loads(row["tcp_file_hashes_json"] or "[]")
    finally:
        conn.close()


def add_tcp_hash(period_id: str, file_hash: str) -> None:
    """Append hash to period's tcp_file_hashes_json."""
    hashes = get_tcp_hashes(period_id)
    if file_hash in hashes:
        return
    hashes.append(file_hash)
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE periods SET tcp_file_hashes_json = ? WHERE id = ?",
            (json.dumps(hashes), period_id),
        )
        conn.commit()
    finally:
        conn.close()


def is_duplicate_tcp(period_id: str, file_hash: str) -> bool:
    """Return True if this TCP file hash already exists for the period."""
    return file_hash in get_tcp_hashes(period_id)


def update_accrual_snapshot(period_id: str, accrual_json: str) -> None:
    """Replace accrual snapshot for a period."""
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE periods SET accrual_snapshot_json = ? WHERE id = ?",
            (accrual_json, period_id),
        )
        conn.commit()
    finally:
        conn.close()


def insert_hours(period_id: str, rows: list[dict[str, Any]]) -> None:
    """Bulk insert hours rows."""
    conn = get_connection()
    try:
        conn.executemany(
            "INSERT INTO hours (period_id, emp_id, date, hrs, code) VALUES (?, ?, ?, ?, ?)",
            [
                (period_id, r["emp_id"], r["date"], r["hrs"], r["code"])
                for r in rows
            ],
        )
        conn.commit()
    finally:
        conn.close()


def get_hours(period_id: str) -> list[dict[str, Any]]:
    """Fetch all hours for a period."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT emp_id, date, hrs, code FROM hours WHERE period_id = ? ORDER BY emp_id, date",
            (period_id,),
        ).fetchall()
        return [
            {"emp_id": r["emp_id"], "date": r["date"], "hrs": r["hrs"], "code": r["code"]}
            for r in rows
        ]
    finally:
        conn.close()


def get_accrual_snapshot(period_id: str) -> dict | None:
    """Get accrual snapshot as parsed JSON."""
    p = get_period(period_id)
    if not p or not p.get("accrual_snapshot_json"):
        return None
    return json.loads(p["accrual_snapshot_json"])
