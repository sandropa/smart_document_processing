"""Deterministic validation checks. Pure functions."""

TOLERANCE = 0.02  # float comparison slack


def validate(doc: dict, items: list[dict]) -> list[dict]:
    """Run all checks. Returns list of {severity, field, message}."""
    return [
        *_check_line_math(items),
        *_check_totals(doc, items),
    ]


def has_errors(issues: list[dict]) -> bool:
    return any(i["severity"] == "error" for i in issues)


def _issue(severity: str, field: str, message: str) -> dict:
    return {"severity": severity, "field": field, "message": message}


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
