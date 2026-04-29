"""Unit tests for validators.py. Run with `python -m unittest`."""
import unittest

from validators import (
    _check_dates,
    _check_duplicate_number,
    _check_line_math,
    _check_missing_fields,
    _check_totals,
    has_errors,
    validate,
)


class TestLineMath(unittest.TestCase):
    def test_correct_math(self):
        self.assertEqual(_check_line_math([{"qty": 2, "price": 5, "total": 10}]), [])

    def test_wrong_math(self):
        issues = _check_line_math([{"qty": 2, "price": 5, "total": 11}])
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["severity"], "error")

    def test_within_tolerance(self):
        # 2 * 5.001 = 10.002 vs total 10.00 → diff 0.002, under 0.02 slack
        self.assertEqual(_check_line_math([{"qty": 2, "price": 5.001, "total": 10}]), [])


class TestTotals(unittest.TestCase):
    def test_clean(self):
        doc = {"subtotal": 10, "tax": 2, "total": 12}
        self.assertEqual(_check_totals(doc, [{"total": 10}]), [])

    def test_subtotal_mismatch(self):
        doc = {"subtotal": 99, "tax": 0, "total": 99}
        issues = _check_totals(doc, [{"total": 50}])
        self.assertTrue(any("Subtotal" in i["message"] for i in issues))

    def test_total_mismatch(self):
        doc = {"subtotal": 100, "tax": 20, "total": 99}
        issues = _check_totals(doc, [])
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["field"], "total")

    def test_skip_subtotal_check_when_no_items(self):
        # No line items means we can't compare line_sum to subtotal.
        doc = {"subtotal": 100, "tax": 0, "total": 100}
        self.assertEqual(_check_totals(doc, []), [])


class TestMissingFields(unittest.TestCase):
    def test_all_present(self):
        doc = {"supplier": "Acme", "number": "1", "issue_date": "2026-01-01", "currency": "EUR"}
        self.assertEqual(_check_missing_fields(doc), [])

    def test_all_missing(self):
        self.assertEqual(len(_check_missing_fields({})), 4)

    def test_blank_string_counts_as_missing(self):
        doc = {"supplier": "  ", "number": "1", "issue_date": "2026-01-01", "currency": "EUR"}
        issues = _check_missing_fields(doc)
        self.assertEqual([i["field"] for i in issues], ["supplier"])


class TestDates(unittest.TestCase):
    def test_valid_dates(self):
        self.assertEqual(_check_dates({"issue_date": "2026-01-01", "due_date": "2026-02-01"}), [])

    def test_bad_format(self):
        issues = _check_dates({"issue_date": "01/01/2026", "due_date": ""})
        self.assertEqual([i["field"] for i in issues], ["issue_date"])

    def test_due_before_issue(self):
        issues = _check_dates({"issue_date": "2026-02-01", "due_date": "2026-01-01"})
        self.assertEqual([i["field"] for i in issues], ["due_date"])

    def test_blank_dates_are_silent(self):
        # Missing fields are caught by _check_missing_fields; date check should not double up.
        self.assertEqual(_check_dates({"issue_date": "", "due_date": ""}), [])


class TestDuplicateNumber(unittest.TestCase):
    def test_no_duplicate(self):
        self.assertEqual(_check_duplicate_number({"number": "X1"}, {"Y1", "Y2"}), [])

    def test_duplicate(self):
        issues = _check_duplicate_number({"number": "X1"}, {"X1"})
        self.assertEqual([i["field"] for i in issues], ["number"])

    def test_blank_number_is_not_duplicate(self):
        self.assertEqual(_check_duplicate_number({"number": ""}, {"X1"}), [])


class TestValidateOrchestrator(unittest.TestCase):
    def test_clean_doc(self):
        doc = {
            "supplier": "Acme", "number": "INV-1", "issue_date": "2026-01-01",
            "due_date": "", "currency": "EUR",
            "subtotal": 100, "tax": 20, "total": 120,
        }
        items = [{"qty": 2, "price": 50, "total": 100}]
        self.assertEqual(validate(doc, items, set()), [])

    def test_intentionally_broken_invoice(self):
        # Mirrors the bug in invoice_1.pdf: total off, fields filled, line items right.
        doc = {
            "supplier": "Acme", "number": "INV-1", "issue_date": "2026-01-01",
            "due_date": "", "currency": "EUR",
            "subtotal": 645, "tax": 129, "total": 800,
        }
        items = [{"qty": 5, "price": 129, "total": 645}]
        issues = validate(doc, items, set())
        fields = [i["field"] for i in issues]
        self.assertEqual(fields, ["total"])

    def test_has_errors(self):
        self.assertTrue(has_errors([{"severity": "error"}]))
        self.assertFalse(has_errors([{"severity": "warning"}]))
        self.assertFalse(has_errors([]))


if __name__ == "__main__":
    unittest.main()
