"""Document parsers."""
import re

import pandas as pd
import pypdf

from db import to_float


def parse_file(file, filename: str) -> tuple[dict, list[dict]]:
    """Dispatch to the right parser by filename extension."""
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if ext == "csv":
        return parse_csv(file, filename)
    if ext == "pdf":
        return parse_pdf(file, filename)
    raise ValueError(f"Unsupported file type: .{ext}")

# Canonical column name -> accepted header variants (lowercased + stripped).
COLUMN_SYNONYMS: dict[str, list[str]] = {
    "description": ["description", "desc", "item", "name", "product"],
    "qty": ["qty", "quantity", "count", "units"],
    "price": ["price", "unit_price", "unit price", "rate", "cost"],
    "total": ["total", "amount", "line_total", "line total", "sum"],
}
REQUIRED = ["qty", "price", "total"]  # description is optional


def _resolve_columns(headers: list[str]) -> dict[str, str]:
    """Map canonical name -> the actual header found in the CSV."""
    resolved: dict[str, str] = {}
    for canonical, synonyms in COLUMN_SYNONYMS.items():
        for h in headers:
            if h in synonyms:
                resolved[canonical] = h
                break
    return resolved


def parse_csv(file, filename: str) -> tuple[dict, list[dict]]:
    """CSV = line items only. Compute subtotal; metadata starts blank."""
    df = pd.read_csv(file)
    df.columns = [str(c).strip().lower() for c in df.columns]
    headers = list(df.columns)
    resolved = _resolve_columns(headers)

    missing = [c for c in REQUIRED if c not in resolved]
    if missing:
        accepted = "; ".join(f"{c}: {COLUMN_SYNONYMS[c]}" for c in missing)
        raise ValueError(
            f"CSV is missing required column(s): {missing}. "
            f"Found headers: {headers}. "
            f"Accepted synonyms — {accepted}."
        )

    desc_col = resolved.get("description")
    items = [
        {
            "description": str(r.get(desc_col, "")) if desc_col else "",
            "qty": to_float(r.get(resolved["qty"])),
            "price": to_float(r.get(resolved["price"])),
            "total": to_float(r.get(resolved["total"])),
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
        "currency": "",
        "subtotal": subtotal,
        "tax": 0.0,
        "total": subtotal,
        "status": "uploaded",
        "source_filename": filename,
    }
    return doc, items


# --- PDF parser (matches our sample invoices/POs) ---

_PDF_HEADERS = ("description", "qty", "unit price", "total")


def parse_pdf(file, filename: str) -> tuple[dict, list[dict]]:
    """Parse our invoice / PO PDF format. Missing fields default to blank/0."""
    reader = pypdf.PdfReader(file)
    text = "\n".join((page.extract_text() or "") for page in reader.pages)
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        raise ValueError("PDF has no extractable text")

    doc_type = "purchase_order" if lines[0].lower().startswith("purchase") else "invoice"

    supplier = number = issue_date = ""
    for line in lines:
        if m := re.match(r"^supplier:\s*(.+)$", line, re.I):
            supplier = m.group(1).strip()
        elif m := re.match(r"^number:\s*(.+)$", line, re.I):
            number = m.group(1).strip()
        elif m := re.match(r"^date:\s*(.+)$", line, re.I):
            issue_date = m.group(1).strip()

    # Locate the line-item table: 4 column-header lines, then rows in groups of 4,
    # ending at "Subtotal".
    items_start = None
    for i in range(len(lines) - 3):
        window = tuple(lines[i + k].lower() for k in range(4))
        if window == _PDF_HEADERS:
            items_start = i + 4
            break

    items_end = lines.index("Subtotal") if "Subtotal" in lines else None

    items: list[dict] = []
    if items_start is not None and items_end is not None and items_start < items_end:
        chunk = lines[items_start:items_end]
        for j in range(0, len(chunk), 4):
            row = chunk[j : j + 4]
            if len(row) < 4:
                break
            desc, qty, price, ltotal = row
            items.append({
                "description": desc,
                "qty": to_float(qty),
                "price": to_float(price),
                "total": to_float(ltotal),
            })

    # Subtotal / tax / grand total appear bottom of file in fixed order.
    subtotal = tax = total = 0.0
    if items_end is not None and items_end + 1 < len(lines):
        subtotal = to_float(lines[items_end + 1])
    for i, line in enumerate(lines):
        if line.lower().startswith("tax"):
            if i + 1 < len(lines):
                tax = to_float(lines[i + 1])
            for j in range(i + 2, len(lines)):
                if lines[j].lower() == "total":
                    if j + 1 < len(lines):
                        total = to_float(lines[j + 1])
                    break
            break

    return {
        "type": doc_type,
        "supplier": supplier,
        "number": number,
        "issue_date": issue_date,
        "due_date": "",
        "currency": "",
        "subtotal": subtotal,
        "tax": tax,
        "total": total,
        "status": "uploaded",
        "source_filename": filename,
    }, items
