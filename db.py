"""SQLite schema + CRUD."""
import sqlite3
from pathlib import Path

import pandas as pd

DB_PATH = Path(__file__).parent / "data.db"
STATUSES = ["uploaded", "needs_review", "validated", "rejected"]
DOC_TYPES = ["invoice", "purchase_order"]


def to_float(x) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT,
                supplier TEXT,
                number TEXT,
                issue_date TEXT,
                due_date TEXT,
                currency TEXT,
                subtotal REAL,
                tax REAL,
                total REAL,
                status TEXT DEFAULT 'uploaded',
                source_filename TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS line_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id INTEGER NOT NULL,
                description TEXT,
                qty REAL,
                price REAL,
                total REAL,
                FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
            );
        """)


def insert_document(doc: dict, items: list[dict]) -> int:
    with _connect() as conn:
        cur = conn.execute(
            """INSERT INTO documents
               (type, supplier, number, issue_date, due_date, currency,
                subtotal, tax, total, status, source_filename)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (doc["type"], doc["supplier"], doc["number"], doc["issue_date"],
             doc["due_date"], doc["currency"], doc["subtotal"], doc["tax"],
             doc["total"], doc["status"], doc.get("source_filename")),
        )
        doc_id = cur.lastrowid
        _replace_items(conn, doc_id, items)
        return doc_id


def update_document(doc_id: int, doc: dict, items: list[dict]) -> None:
    with _connect() as conn:
        conn.execute(
            """UPDATE documents
               SET type=?, supplier=?, number=?, issue_date=?, due_date=?,
                   currency=?, subtotal=?, tax=?, total=?, status=?
               WHERE id=?""",
            (doc["type"], doc["supplier"], doc["number"], doc["issue_date"],
             doc["due_date"], doc["currency"], doc["subtotal"], doc["tax"],
             doc["total"], doc["status"], doc_id),
        )
        _replace_items(conn, doc_id, items)


def _replace_items(conn: sqlite3.Connection, doc_id: int, items: list[dict]) -> None:
    conn.execute("DELETE FROM line_items WHERE document_id=?", (doc_id,))
    for it in items:
        conn.execute(
            """INSERT INTO line_items (document_id, description, qty, price, total)
               VALUES (?,?,?,?,?)""",
            (doc_id, it.get("description") or "",
             to_float(it.get("qty")), to_float(it.get("price")), to_float(it.get("total"))),
        )


def list_documents() -> pd.DataFrame:
    with _connect() as conn:
        return pd.read_sql_query(
            """SELECT id, type, supplier, number, currency, total, status, created_at
               FROM documents ORDER BY id DESC""",
            conn,
        )


def get_document(doc_id: int) -> dict | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()
        if row is None:
            return None
        doc = dict(row)
        items = conn.execute(
            "SELECT description, qty, price, total FROM line_items WHERE document_id=? ORDER BY id",
            (doc_id,),
        ).fetchall()
        doc["items"] = [dict(i) for i in items]
        return doc
