"""Deterministic validation checks. Pure functions."""
from datetime import date

TOLERANCE = 0.02  # float comparison slack
REQUIRED_FIELDS = ("supplier", "number", "issue_date", "currency")


def validate(
    doc: dict,
    items: list[dict],
    existing_numbers: set[str] | None = None,
) -> list[dict]:
    """Run all checks. Returns list of {severity, field, message}."""
    existing_numbers = existing_numbers or set()
    return [
        *_check_missing_fields(doc),
        *_check_dates(doc),
        *_check_duplicate_number(doc, existing_numbers),
        *_check_line_math(items),
        *_check_totals(doc, items),
    ]


def has_errors(issues: list[dict]) -> bool:
    return any(i["severity"] == "error" for i in issues)


def _issue(severity: str, field: str, message: str) -> dict:
    return {"severity": severity, "field": field, "message": message}


def _check_missing_fields(doc: dict) -> list[dict]:
    issues = []
    for field in REQUIRED_FIELDS:
        if not str(doc.get(field) or "").strip():
            issues.append(_issue("error", field, f"{field} is missing"))
    return issues


def _check_dates(doc: dict) -> list[dict]:
    issues = []
    raw_issue = doc.get("issue_date")
    raw_due = doc.get("due_date")
    issue_dt = _parse_date(raw_issue)
    due_dt = _parse_date(raw_due)
    if raw_issue and issue_dt is None:
        issues.append(_issue("error", "issue_date",
                             "issue_date is not a valid date (use YYYY-MM-DD)"))
    if raw_due and due_dt is None:
        issues.append(_issue("error", "due_date",
                             "due_date is not a valid date (use YYYY-MM-DD)"))
    if issue_dt and due_dt and due_dt < issue_dt:
        issues.append(_issue("error", "due_date",
                             "due_date is before issue_date"))
    return issues


def _parse_date(s) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(str(s).strip())
    except (ValueError, TypeError):
        return None


def _check_duplicate_number(doc: dict, existing_numbers: set[str]) -> list[dict]:
    num = str(doc.get("number") or "").strip()
    if num and num in existing_numbers:
        return [_issue("error", "number", f"Document number '{num}' already exists")]
    return []


def _check_line_math(items: list[dict]) -> list[dict]:
    issues = []
    for idx, it in enumerate(items, start=1):
        qty = _f(it.get("qty"))
        price = _f(it.get("price"))
        total = _f(it.get("total"))
        expected = qty * price
        if abs(expected - total) > TOLERANCE:
            issues.append(_issue(
                "error", f"line_item[{idx}].total",
                f"Line {idx}: qty × price = {expected:.2f}, but total is {total:.2f}",
            ))
    return issues


def _check_totals(doc: dict, items: list[dict]) -> list[dict]:
    issues = []
    line_sum = sum(_f(it.get("total")) for it in items)
    subtotal = _f(doc.get("subtotal"))
    tax = _f(doc.get("tax"))
    total = _f(doc.get("total"))
    if items and abs(line_sum - subtotal) > TOLERANCE:
        issues.append(_issue(
            "error", "subtotal",
            f"Subtotal {subtotal:.2f} ≠ sum of line totals {line_sum:.2f}",
        ))
    if abs((subtotal + tax) - total) > TOLERANCE:
        issues.append(_issue(
            "error", "total",
            f"Total {total:.2f} ≠ subtotal {subtotal:.2f} + tax {tax:.2f} ({subtotal + tax:.2f})",
        ))
    return issues


def _f(x) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0
