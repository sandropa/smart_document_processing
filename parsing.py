"""Document parsers. v1: CSV only."""
import pandas as pd

from db import to_float

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
        "currency": "EUR",
        "subtotal": subtotal,
        "tax": 0.0,
        "total": subtotal,
        "status": "uploaded",
        "source_filename": filename,
    }
    return doc, items
