"""Streamlit UI."""
import pandas as pd
import streamlit as st

from auth import require_password
from db import (
    DOC_TYPES,
    STATUSES,
    get_document,
    init_db,
    insert_document,
    list_documents,
    to_float,
    update_document,
)
from parsing import parse_csv
from validators import has_errors, validate


def _status_for(issues: list[dict]) -> str:
    return "needs_review" if has_errors(issues) else "validated"


def render_issues(issues: list[dict]) -> None:
    if not issues:
        st.success("No validation issues.")
        return
    errors = [i for i in issues if i["severity"] == "error"]
    warnings = [i for i in issues if i["severity"] == "warning"]
    if errors:
        st.error(f"{len(errors)} error(s)")
        for i in errors:
            st.markdown(f"- **{i['field']}** — {i['message']}")
    if warnings:
        st.warning(f"{len(warnings)} warning(s)")
        for i in warnings:
            st.markdown(f"- **{i['field']}** — {i['message']}")


def render_upload_tab() -> None:
    # After save, swap the uploader UI for a confirmation + reset button.
    if "saved_doc_id" in st.session_state:
        st.success(
            f"Saved as document #{st.session_state['saved_doc_id']}. "
            "Find it in the Dashboard or Detail / Edit tab."
        )
        if st.button("Upload another"):
            st.session_state.pop("saved_doc_id", None)
            # Bumping the key resets the file_uploader widget state.
            st.session_state["uploader_key"] = st.session_state.get("uploader_key", 0) + 1
            st.rerun()
        return

    key = f"uploader_{st.session_state.get('uploader_key', 0)}"
    uploaded = st.file_uploader("Upload a CSV", type=["csv"], key=key)
    if uploaded is None:
        return

    try:
        doc, items = parse_csv(uploaded, uploaded.name)
    except ValueError as e:
        st.error(f"Could not parse `{uploaded.name}`: {e}")
        return
    except Exception as e:
        st.error(f"Could not read `{uploaded.name}`: {e}")
        return

    st.write("**Preview**")
    st.json(doc)
    st.dataframe(pd.DataFrame(items), use_container_width=True)

    issues = validate(doc, items)
    st.write("**Validation**")
    render_issues(issues)

    if st.button("Save to database", type="primary"):
        doc["status"] = _status_for(issues)
        st.session_state["saved_doc_id"] = insert_document(doc, items)
        st.rerun()


def render_dashboard_tab() -> None:
    docs = list_documents()
    if docs.empty:
        st.info("No documents yet.")
    else:
        st.dataframe(docs, use_container_width=True, hide_index=True)


def render_detail_tab() -> None:
    docs = list_documents()
    if docs.empty:
        st.info("Upload something first.")
        return

    ids = docs["id"].tolist()
    selected = int(st.selectbox("Document", ids, format_func=lambda i: f"#{i}"))
    doc = get_document(selected)
    if not doc:
        return

    st.write("**Validation**")
    render_issues(validate(doc, doc["items"]))

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
            doc["subtotal"] = st.number_input("Subtotal", value=to_float(doc["subtotal"]))
            doc["tax"] = st.number_input("Tax", value=to_float(doc["tax"]))
            doc["total"] = st.number_input("Total", value=to_float(doc["total"]))

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
            new_items = items_df.to_dict(orient="records")
            issues = validate(doc, new_items)
            # Re-validate: auto-flip between needs_review/validated unless user chose rejected.
            if doc["status"] != "rejected":
                doc["status"] = _status_for(issues)
            update_document(selected, doc, new_items)
            st.success(f"Saved. Status: {doc['status']}.")


st.set_page_config(page_title="Smart Document Processing", layout="wide")
require_password()
init_db()
st.title("Smart Document Processing")

tab_upload, tab_dashboard, tab_detail = st.tabs(["Upload", "Dashboard", "Detail / Edit"])
with tab_upload:
    render_upload_tab()
with tab_dashboard:
    render_dashboard_tab()
with tab_detail:
    render_detail_tab()
