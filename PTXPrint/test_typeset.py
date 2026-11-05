"""Source conversion and command-line failure checks; no XeTeX required."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from typeset import HERE, USFMWriter, dimensions, paired_book, paper_size, prepare, verify_note_pages, note_plan


class DriverTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def source(self, edition, verses):
        subdir = "translatedTexts/ReadersVersion" if edition == "RV" else "derivedTexts/auto_edited_VLT_ESFM"
        path = self.root / subdir / f"OET-{edition}_MRK.ESFM"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"\\id MRK\n\\h Markos\n\\mt1 {edition} title\n\\c 1\n{verses}\n")

    def test_paper_dimensions(self):
        self.assertEqual(dimensions(paper_size("Letter")), ("8.5in", "11in"))
        self.assertEqual(dimensions(paper_size("A4")), ("210mm", "297mm"))
        self.assertEqual(dimensions(paper_size("B5")), ("176mm", "250mm"))
        self.assertEqual(dimensions(paper_size("6 x 9 inches")), ("6in", "9in"))
        self.assertEqual(dimensions(paper_size("160x240mm")), ("160mm", "240mm"))

    def test_bridge_and_notes_survive_conversion(self):
        self.source("RV", "\\s1 A heading\n\\r Mat. 1:2\n\\p\n\\v 1-2 Readers’ text.\\f + \\fr 1:1 \\ft A note.\\f*")
        self.source("LV", "\\v 1 Literal_text.\n\\v 2 Second.")
        writer = USFMWriter()
        intro, body = writer.book(paired_book(self.root, "MRK"))
        self.assertIn("\\lefttext", body)
        self.assertIn("\\righttext", body)
        self.assertIn("\\v 1-2", body)
        self.assertIn("\\v 1 Literal_text.", body)
        self.assertIn("\\v 2 Second.", body)
        self.assertIn("\\s1 A heading\\sup 1\\sup*", body)
        self.assertIn("\\f - \\ft 1", body)
        self.assertEqual([n["text"] for n in writer.notes], ["Mat. 1:2", "A note."])

    def test_single_edition_needs_only_its_own_source(self):
        self.source("LV", "\\v 1 Literal_text.\n\\v 2")
        directory = self.root / "build"
        directory.mkdir()
        prepare(directory, [paired_book(self.root, "MRK", "OET-LV")], "letter", "OET-LV")
        body = (directory / "MRK.usfm").read_text()
        self.assertNotIn("\\lefttext", body)
        self.assertNotIn("\\righttext", body)
        self.assertIn("◘", body)
        self.assertIn("\\PaperWidth=8.5in", (directory / "proof.tex").read_text())
        self.assertEqual(json.loads((directory / "notes.json").read_text()), [])

    def test_revision_lines_follow_the_book_text(self):
        self.source('RV', '\\v 1 Readers’ ending.')
        self.source('LV', '\\v 1 Literal_ending.')
        book = paired_book(self.root, 'MRK')
        book.set('rv-source-version', 'v1.2.3')
        book.set('draft-credit', 'Open English Translation · Translation draft v9.8.7 · OET.Bible')
        intro, body = USFMWriter().book(book)
        self.assertIn('Translation draft v9.8.7', intro)
        self.assertNotIn('Translation draft', body)
        self.assertGreater(body.index('\\zbookend MRK · OET-RV v1.2.3'), body.index('Literal_ending.'))
        self.assertIn('\\righttext\n\\zbookend MRK · OET-LV version not specified in source ID', body)

    def test_chapter_start_with_a_late_first_verse_keeps_the_chapter_label(self):
        self.source('LV', '\\v 26 First supplied verse.\n\\v 27 Next.')
        book = paired_book(self.root, 'MRK', 'OET-LV')
        self.assertEqual(book.find('.//block').get('chapter-start'), 'true')
        _, body = USFMWriter().book(book)
        self.assertIn('\\OETFirstVerseLabel 26 ', body)
        self.assertNotIn('\\OETFirstVerseLabel 27 ', body)

    def test_failed_render_preserves_existing_pdf_and_keeps_diagnostics(self):
        self.source("RV", "\\v 1 Readers’ text.")
        macros = self.root / "macros"
        macros.mkdir()
        for filename in ("paratext2.tex", "ptx2pdf.sty"):
            (macros / filename).touch()
        output = self.root / "existing.pdf"
        output.write_bytes(b"existing PDF")
        result = subprocess.run([sys.executable, str(HERE / "typeset.py"), "MRK", "--version", "OET-RV",
                                 "--oet-root", str(self.root), "--ptxprint-root", str(macros),
                                 "--xetex", "/bin/false", "--xdvipdfmx", "/bin/true",
                                 "--build-dir", str(self.root / "build"), "-o", str(output)],
                                capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("XeTeX failed", result.stderr)
        self.assertEqual(output.read_bytes(), b"existing PDF")
        self.assertTrue((self.root / "build" / "proof.tex").is_file())

    def test_note_locations_must_be_complete_unique_and_on_the_calling_page(self):
        caller = r"\@noteid{1}{f}{c}{31}{100}{200}"
        note = r"\@noteid{1}{f}{n}{31}{100}{20}"
        verify_note_pages(caller + note, 1)
        verify_note_pages("", 0)
        for records, count in [(caller + note.replace("{31}", "{32}"), 1),
                               (caller, 1), (caller + note + note, 1),
                               (caller + note, 2)]:
            with self.subTest(records=records, count=count), self.assertRaises(ValueError):
                verify_note_pages(records, count)

    def test_note_plan_uses_calling_pages_and_retains_grid_reservations(self):
        reserves = {}
        records = r'\@noteid{1}{f}{c}{3}\@noteid{2}{f}{c}{4}'
        heights = {1: 25.09375, 2: 12.546875}  # Two and one 12.5bp lines.
        callers, groups = note_plan(records, heights, reserves)
        self.assertEqual(callers, {1: 3, 2: 4})
        self.assertEqual(groups, {3: [1], 4: [2]})
        self.assertEqual(reserves, {3: 37.5, 4: 25.0})
        note_plan(records.replace('{c}{3}', '{c}{4}'), heights, reserves)
        self.assertEqual(reserves, {3: 37.5, 4: 50.0})
        for invalid in [records + r'\@noteid{1}{f}{c}{4}', r'\@noteid{1}{f}{c}{3}']:
            with self.assertRaises(ValueError):
                note_plan(invalid, heights, {})


if __name__ == "__main__":
    unittest.main()
