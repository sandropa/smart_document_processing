"""Minimal v1: CSV upload -> parse -> SQLite -> list/edit/save."""
import hmac
import sqlite3
from pathlib import Path

import pandas as pd
import streamlit as st

DB_PATH = Path(__file__).parent / "data.db"
STATUSES = ["uploaded", "needs_review", "validated", "rejected"]
DOC_TYPES = ["invoice", "purchase_order"]


# --- DB ---

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db() as conn:
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
    with db() as conn:
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
    with db() as conn:
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


def _replace_items(conn, doc_id: int, items: list[dict]) -> None:
    conn.execute("DELETE FROM line_items WHERE document_id=?", (doc_id,))
    for it in items:
        conn.execute(
            """INSERT INTO line_items (document_id, description, qty, price, total)
               VALUES (?,?,?,?,?)""",
            (doc_id, it.get("description") or "",
             _num(it.get("qty")), _num(it.get("price")), _num(it.get("total"))),
        )


def list_documents() -> pd.DataFrame:
    with db() as conn:
        return pd.read_sql_query(
            """SELECT id, type, supplier, number, currency, total, status, created_at
               FROM documents ORDER BY id DESC""",
            conn,
        )


def get_document(doc_id: int) -> dict | None:
    with db() as conn:
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


def _num(x) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


# --- Parsing ---

def parse_csv(file, filename: str) -> tuple[dict, list[dict]]:
    """CSV is line items only. We compute subtotal; metadata starts blank."""
    df = pd.read_csv(file)
    df.columns = [c.strip().lower() for c in df.columns]
    items = [
        {
            "description": str(r.get("desc", r.get("description", ""))),
            "qty": _num(r.get("qty")),
            "price": _num(r.get("price")),
            "total": _num(r.get("total")),
        }
        for r in df.to_dict(orient="records")
    ]
    subtotal = sum(it["total"] for it in items)
    doc = {
        "type": "invoice",
        "supplier": "",
        "number": "",
        "issue_date": "",
        "due_date": "",
        "currency": "EUR",
        "subtotal": subtotal,
        "tax": 0.0,
        "total": subtotal,
        "status": "uploaded",
        "source_filename": filename,
    }
    return doc, items


# --- Auth ---

def require_password() -> None:
    """Single shared password from st.secrets['app_password']. Halts the app until match."""
    if st.session_state.get("authed"):
        return
    expected = st.secrets.get("app_password")
    if not expected:
        st.error("`app_password` is not set in Streamlit secrets.")
        st.stop()
    pw = st.text_input("Password", type="password")
    if pw:
        if hmac.compare_digest(pw, expected):
            st.session_state["authed"] = True
            st.rerun()
        else:
            st.error("Wrong password")
    st.stop()


# --- UI ---

st.set_page_config(page_title="Smart Document Processing", layout="wide")
require_password()
init_db()
st.title("Smart Document Processing")

tab_upload, tab_dashboard, tab_detail = st.tabs(["Upload", "Dashboard", "Detail / Edit"])

with tab_upload:
    uploaded = st.file_uploader("Upload a CSV", type=["csv"])
    if uploaded is not None:
        doc, items = parse_csv(uploaded, uploaded.name)
        st.write("**Preview**")
        st.json({k: v for k, v in doc.items() if k != "items"})
        st.dataframe(pd.DataFrame(items), use_container_width=True)
        if st.button("Save to database", type="primary"):
            new_id = insert_document(doc, items)
            st.success(f"Saved as document #{new_id}. Open it in 'Detail / Edit'.")

with tab_dashboard:
    docs = list_documents()
    if docs.empty:
        st.info("No documents yet.")
    else:
        st.dataframe(docs, use_container_width=True, hide_index=True)

with tab_detail:
    docs = list_documents()
    if docs.empty:
        st.info("Upload something first.")
    else:
        ids = docs["id"].tolist()
        selected = st.selectbox("Document", ids, format_func=lambda i: f"#{i}")
        doc = get_document(int(selected))
        if doc:
            with st.form("edit_doc"):
                c1, c2, c3 = st.columns(3)
                with c1:
                    doc["type"] = st.selectbox(
                        "Type", DOC_TYPES,
                        index=DOC_TYPES.index(doc["type"]) if doc["type"] in DOC_TYPES else 0,
                    )
                    doc["supplier"] = st.text_input("Supplier", doc["supplier"] or "")
                    doc["number"] = st.text_input("Number", doc["number"] or "")
                with c2:
                    doc["issue_date"] = st.text_input("Issue date", doc["issue_date"] or "")
                    doc["due_date"] = st.text_input("Due date", doc["due_date"] or "")
                    doc["currency"] = st.text_input("Currency", doc["currency"] or "")
                with c3:
                    doc["subtotal"] = st.number_input("Subtotal", value=_num(doc["subtotal"]))
                    doc["tax"] = st.number_input("Tax", value=_num(doc["tax"]))
                    doc["total"] = st.number_input("Total", value=_num(doc["total"]))

                doc["status"] = st.selectbox(
                    "Status", STATUSES,
                    index=STATUSES.index(doc["status"]) if doc["status"] in STATUSES else 0,
                )

                st.write("**Line items**")
                items_df = st.data_editor(
                    pd.DataFrame(doc["items"]) if doc["items"]
                    else pd.DataFrame(columns=["description", "qty", "price", "total"]),
                    num_rows="dynamic",
                    use_container_width=True,
                )

                if st.form_submit_button("Save changes", type="primary"):
                    update_document(int(selected), doc, items_df.to_dict(orient="records"))
                    st.success("Saved.")
