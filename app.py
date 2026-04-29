"""Streamlit UI."""
import pandas as pd
import streamlit as st

from auth import require_password
from db import (
    CURRENCIES,
    DOC_TYPES,
    STATUSES,
    existing_numbers,
    get_document,
    init_db,
    insert_document,
    list_documents,
    to_float,
    update_document,
)
from parsing import parse_file
from validators import has_errors, validate


def _status_for(issues: list[dict]) -> str:
    return "needs_review" if has_errors(issues) else "validated"


def _docs_with_issue_counts() -> pd.DataFrame:
    """List docs + a count of error-severity issues per row."""
    docs = list_documents()
    if docs.empty:
        return docs
    all_numbers = existing_numbers()
    counts = []
    for doc_id in docs["id"]:
        full = get_document(int(doc_id))
        own = (full.get("number") or "").strip() if full else ""
        others = all_numbers - ({own} if own else set())
        issues = validate(full, full["items"], others) if full else []
        counts.append(sum(1 for i in issues if i["severity"] == "error"))
    docs.insert(len(docs.columns) - 1, "issues", counts)
    return docs


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
    uploaded = st.file_uploader(
        "Upload a CSV, PDF, TXT, or image",
        type=["csv", "pdf", "txt", "png", "jpg", "jpeg"],
        key=key,
    )
    if uploaded is None:
        return

    is_image = uploaded.name.lower().rsplit(".", 1)[-1] in ("png", "jpg", "jpeg")
    api_key = st.secrets.get("openrouter_key", "")
    try:
        if is_image:
            with st.spinner("Running OCR via OpenRouter…"):
                doc, items = parse_file(uploaded, uploaded.name, api_key=api_key)
        else:
            doc, items = parse_file(uploaded, uploaded.name)
    except ValueError as e:
        st.error(f"Could not parse `{uploaded.name}`: {e}")
        return
    except Exception as e:
        st.error(f"Could not read `{uploaded.name}`: {e}")
        return

    st.write("**Preview**")
    st.json(doc)
    st.dataframe(pd.DataFrame(items), use_container_width=True)

    issues = validate(doc, items, existing_numbers())
    st.write("**Validation**")
    render_issues(issues)

    if st.button("Save to database", type="primary"):
        doc["status"] = _status_for(issues)
        st.session_state["saved_doc_id"] = insert_document(doc, items)
        st.rerun()


def render_dashboard_tab() -> None:
    docs = _docs_with_issue_counts()
    if docs.empty:
        st.info("No documents yet.")
        return
    status_filter = st.selectbox(
        "Filter by status", ["all", *STATUSES], index=0, key="dash_status_filter",
    )
    if status_filter != "all":
        docs = docs[docs["status"] == status_filter]
    st.dataframe(docs, use_container_width=True, hide_index=True)


def render_detail_tab() -> None:
    # Toast carried over from the previous run (after save + rerun).
    msg = st.session_state.pop("detail_save_msg", None)
    if msg:
        st.success(msg)

    docs = list_documents()
    if docs.empty:
        st.info("Upload something first.")
        return

    # Default to needs_review when any exist, so this tab acts as a review queue.
    options = ["all", *STATUSES]
    has_review = (docs["status"] == "needs_review").any()
    default_idx = options.index("needs_review") if has_review else 0
    status_filter = st.selectbox(
        "Filter by status", options, index=default_idx, key="detail_status_filter",
    )
    if status_filter != "all":
        docs = docs[docs["status"] == status_filter]
    if docs.empty:
        st.info(f"No documents with status `{status_filter}`.")
        return

    ids = docs["id"].tolist()
    selected = int(st.selectbox("Document", ids, format_func=lambda i: f"#{i}"))
    doc = get_document(selected)
    if not doc:
        return

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
            currency_options = ["", *CURRENCIES]
            # Preserve unknown currency values that came from elsewhere (e.g. legacy uploads).
            if doc["currency"] and doc["currency"] not in currency_options:
                currency_options.append(doc["currency"])
            doc["currency"] = st.selectbox(
                "Currency", currency_options,
                index=currency_options.index(doc["currency"]) if doc["currency"] in currency_options else 0,
            )
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

        b1, b2 = st.columns(2)
        validate_clicked = b1.form_submit_button("Validate")
        save_clicked = b2.form_submit_button("Save changes", type="primary")

    # Read form values whether or not a button was clicked (initial render uses DB state).
    new_items = items_df.to_dict(orient="records")
    issues = validate(doc, new_items, existing_numbers(exclude_id=selected))

    if save_clicked:
        if doc["status"] != "rejected":
            doc["status"] = _status_for(issues)
        update_document(selected, doc, new_items)
        st.session_state["detail_save_msg"] = f"Saved. Status: {doc['status']}."
        st.rerun()

    if validate_clicked and not has_errors(issues) and doc["status"] != "rejected":
        doc["status"] = "validated"
        update_document(selected, doc, new_items)
        st.session_state["detail_save_msg"] = "Validation passed — status set to validated."
        st.rerun()

    st.write("**Validation**")
    render_issues(issues)


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
