# Smart Document Processing

Streamlit app that ingests business documents (invoices and purchase orders),
extracts structured fields, validates them, and lets you fix issues through a
review interface.

**Live:** https://smartdocumentprocessing.streamlit.app/

## What it does

- Accepts **CSV, PDF, TXT, and images** (PNG/JPG).
- Images go through a two-stage pipeline: fast/free OCR first, falls back to
  `google/gemini-2.5-flash` (via OpenRouter) when the simple format isn't
  detected.
- Validates: line-item math, subtotal/tax/total math, missing required
  fields, date format/order, duplicate document numbers.
- Status workflow: `uploaded` → `needs_review` / `validated` / `rejected`.
  Auto-set on save based on validation; the **Detail / Edit** tab acts as a
  review queue and re-validates on every save.

## How to use it

1. Open the live link, enter the password.
2. **Upload** tab: drop a CSV / PDF / TXT / image. Preview + validation
   appear; click **Save to database**.
3. **Dashboard**: list of all documents with statuses and issue counts.
4. **Detail / Edit**: defaults to `needs_review`, edit fields, click
   **Validate** to re-check or **Save changes**.

## Run locally

```bash
pip install -r requirements.txt

mkdir -p .streamlit && cat > .streamlit/secrets.toml <<EOF
app_password   = "<choose>"
openrouter_key = "<your key>"
EOF

streamlit run app.py
python -m unittest    # tests
```

## Files

`app.py` UI · `db.py` SQLite + CRUD · `parsing.py` per-format parsers and
image OCR pipeline · `validators.py` deterministic checks · `auth.py`
password gate · `test_*.py` unit tests.
