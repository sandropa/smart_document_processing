"""Unit tests for the deterministic parsers (CSV + TXT helper)."""
import io
import unittest

from parsing import _parse_minimal_text, parse_csv


class TestParseCSV(unittest.TestCase):
    def test_basic(self):
        doc, items = parse_csv(io.StringIO("desc,qty,price,total\nA,2,10,20\n"), "x.csv")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["qty"], 2.0)
        self.assertEqual(items[0]["total"], 20.0)
        self.assertEqual(doc["subtotal"], 20.0)
        self.assertEqual(doc["currency"], "")  # we don't guess

    def test_synonyms(self):
        # Quantity/Unit Price/Amount should resolve to qty/price/total.
        doc, items = parse_csv(
            io.StringIO("Item,Quantity,Unit Price,Amount\nWidget,3,5,15\n"), "x.csv",
        )
        self.assertEqual(items[0]["qty"], 3.0)
        self.assertEqual(items[0]["price"], 5.0)
        self.assertEqual(items[0]["total"], 15.0)

    def test_missing_required_raises(self):
        with self.assertRaises(ValueError):
            parse_csv(io.StringIO("desc,qty,price\nA,2,10\n"), "x.csv")


class TestMinimalTextParser(unittest.TestCase):
    def test_two_line_invoice(self):
        doc, items = _parse_minimal_text("Invoice TXT-0\nTotal: 758 EUR", "t.txt")
        self.assertEqual(doc["type"], "invoice")
        self.assertEqual(doc["number"], "TXT-0")
        self.assertEqual(doc["total"], 758.0)
        self.assertEqual(doc["subtotal"], 758.0)  # collapsed: no breakdown in source
        self.assertEqual(doc["currency"], "EUR")
        self.assertEqual(items, [])

    def test_with_supplier_line(self):
        doc, _ = _parse_minimal_text(
            "Invoice 3724\nSupplier Img 0\nTotal: 1123 BAM", "i.png",
        )
        self.assertEqual(doc["supplier"], "Img 0")
        self.assertEqual(doc["number"], "3724")
        self.assertEqual(doc["currency"], "BAM")

    def test_purchase_order(self):
        doc, _ = _parse_minimal_text("Purchase Order PO-1\nTotal: 100 USD", "p.txt")
        self.assertEqual(doc["type"], "purchase_order")
        self.assertEqual(doc["number"], "PO-1")

    def test_strips_bullet_prefixes(self):
        # An LLM might wrap OCR output in markdown; the parser should still cope.
        doc, _ = _parse_minimal_text(
            "- Invoice X1\n- Supplier Foo\n- Total: 42 EUR", "ocr.png",
        )
        self.assertEqual(doc["number"], "X1")
        self.assertEqual(doc["supplier"], "Foo")
        self.assertEqual(doc["total"], 42.0)


if __name__ == "__main__":
    unittest.main()
