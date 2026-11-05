"""Regression checks for paper parsing and independent single-version sources."""
import argparse
from pathlib import Path
import tempfile
import unittest

from typeset import paired_book, paper_size, read_edition


class PaperSizeTests(unittest.TestCase):
    def test_presets(self):
        self.assertEqual(paper_size("A4"), "a4")
        self.assertEqual(paper_size(" b5 "), "b5")
        self.assertEqual(paper_size("Letter"), "letter")

    def test_dimensions(self):
        cases = {
            "210x297mm": "210mm x 297mm",
            "210mm × 297mm": "210mm x 297mm",
            "8.5 X 11 inches": "8.5in x 11in",
            "8.5in x 11in": "8.5in x 11in",
            "6 inch x 9": "6in x 9in",
            "8.5in x 297mm": "8.5in x 297mm",
            ".5in x 9in": ".5in x 9in",
        }
        for value, expected in cases.items():
            with self.subTest(value=value):
                self.assertEqual(paper_size(value), expected)

    def test_invalid_dimensions(self):
        for value in ("", "A0", "0x10in", "-1x9in", "210x297", "8in",
                      "nanx10in", "6x9pt", "6x9in extra", "9" * 400 + "x10mm"):
            with self.subTest(value=value):
                with self.assertRaises(argparse.ArgumentTypeError):
                    paper_size(value)


class VersionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def write_source(self, edition, verses):
        directory = "translatedTexts/ReadersVersion" if edition == "RV" else "derivedTexts/auto_edited_VLT_ESFM"
        path = self.root / directory / f"OET-{edition}_MRK.ESFM"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"\\id MRK\n\\h {edition} name\n\\mt1 {edition} title\n\\c 1\n{verses}\n", encoding="utf-8")

    def test_rv_only_does_not_require_lv(self):
        self.write_source("RV", "\\s1 Heading\n\\r Parallel passage\n\\p\n\\v 1 Readers’ text.")
        book = paired_book(self.root, "MRK", "OET-RV")
        self.assertEqual(book.get("name"), "RV name")
        self.assertEqual(book.get("version"), "OET-RV")
        self.assertIsNone(book.find(".//lv"))
        self.assertEqual(book.find(".//heading/note").get("ref"), "1:1")
        self.assertEqual(book.find(".//rv/block/run").text, "Readers’ text.")

    def test_lv_only_does_not_require_rv(self):
        self.write_source("LV", "\\v 1 Literal_text.\n\\v 2")
        book = paired_book(self.root, "MRK", "OET-LV")
        self.assertEqual(book.get("name"), "LV name")
        self.assertIsNone(book.find(".//rv"))
        self.assertIsNone(book.find(".//heading"))
        self.assertEqual(len(book.findall(".//lv/block")), 2)

    def test_header_names_strip_inline_markers_without_losing_letters(self):
        path = self.root / 'header.ESFM'
        path.write_text('\\h 1 Shəmū\\sup ʼēl\\sup*/(Samuel)\n\\c 1\n\\v 1 Text.\n')
        self.assertEqual(read_edition(path, 'LV').name, '1 Shəmūʼēl/(Samuel)')

    def test_default_pairs_verse_bridges(self):
        self.write_source("RV", "\\s1 Heading\n\\v 1-2 Readers’ text.")
        self.write_source("LV", "\\v 1 First.\n\\v 2 Second.")
        book = paired_book(self.root, "MRK")
        self.assertEqual(book.get("version"), "OET")
        section = book.find("section")
        self.assertEqual(len(section.find("rv")), 1)
        self.assertEqual(len(section.find("lv")), 2)

    def test_paired_coverage_validation_is_preserved(self):
        self.write_source("RV", "\\v 1 Readers’ text.")
        self.write_source("LV", "\\v 2 Literal_text.")
        with self.assertRaisesRegex(ValueError, "verse coverage differs"):
            paired_book(self.root, "MRK")


if __name__ == "__main__":
    unittest.main()
