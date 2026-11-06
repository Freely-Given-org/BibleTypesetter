"""Exercise real SILE page/column breaks and physical-page note placement."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET

from SILE.build_pdfs import renderer_executable
from SILE.typeset import render_sile


class FlowLayoutTests(unittest.TestCase):
    def test_reading_order_grid_and_notes_across_column_breaks(self):
        if not shutil.which('pdftotext'):
            self.skipTest('Poppler is needed for the layout integration check')
        try:
            executable = renderer_executable()
        except ValueError:
            self.skipTest('SILE is needed for the layout integration check')
        root = ET.Element('sile', {'class': 'oet', 'papersize': 'b5'})
        book = ET.SubElement(root, 'book', {'name': 'Fixture', 'code': 'MRK', 'version': 'DEMO',
            'sides': 'rv', 'body-columns': '2', 'edition-title': 'Fixture', 'rv-label': 'Fixture'})
        ET.SubElement(ET.SubElement(book, 'intro', kind='ip'), 'run').text = 'Full width introduction.'
        note_verses = set(range(4, 161, 11))
        for verse in range(1, 161):
            section = ET.SubElement(book, 'section')
            ET.SubElement(ET.SubElement(section, 'heading'), 'run').text = f'Heading{verse:03}'
            block = ET.SubElement(ET.SubElement(section, 'rv'), 'block',
                                  ref=f'1:{verse}', verse=str(verse), para='p')
            ET.SubElement(block, 'run').text = f'Token{verse:03} ' + 'some more text to wrap in a column. ' * 3
            if verse in note_verses:
                note = ET.SubElement(block, 'note', edition='Fixture', ref=f'1:{verse}', kind='Note')
                ET.SubElement(note, 'run').text = f'Note{verse:03} ' + 'Footnote text on the calling physical page. ' * 3
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            render_sile(directory, root, executable)
            xml = subprocess.check_output(['pdftotext', '-bbox', str(directory / 'proof.pdf'), '-'])
        pages = ET.fromstring(xml).findall('.//{*}page')
        tokens, note_pages, token_pages, heading_pages = [], {}, {}, {}
        self.assertGreater(len(pages), 3)
        for page_no, page in enumerate(pages):
            words = page.findall('.//{*}word')
            body = [word for word in words if (word.text or '').startswith('Token')]
            # Reading goes down the left column, then down the right column.
            body.sort(key=lambda w: (float(w.get('xMin')) > float(page.get('width')) / 2,
                                     float(w.get('yMin'))))
            if page_no > 0:
                self.assertTrue(any(float(w.get('xMin')) < float(page.get('width')) / 2 for w in body))
                self.assertTrue(any(float(w.get('xMin')) > float(page.get('width')) / 2 for w in body))
            for word in body:
                verse = int(word.text.removeprefix('Token'))
                tokens.append(verse)
                token_pages[verse] = page_no
            for word in words:
                if (word.text or '').startswith('Note') and word.text[4:].isdigit():
                    note_pages[int(word.text.removeprefix('Note'))] = page_no
                    if body:
                        self.assertGreater(float(word.get('yMin')), max(float(w.get('yMin')) for w in body))
                elif (word.text or '').startswith('Heading'):
                    heading_pages[int(word.text.removeprefix('Heading'))] = page_no
            # Body baselines use the same 12.5pt grid in either column.
            if body:
                base = float(body[0].get('yMin'))
                for word in body:
                    offset = (float(word.get('yMin')) - base) / 12.5
                    self.assertAlmostEqual(offset, round(offset), places=3)
        self.assertEqual(tokens, list(range(1, 161)))
        self.assertEqual(note_pages, {v: token_pages[v] for v in note_verses})
        self.assertEqual(heading_pages, token_pages)

    def test_parallel_columns_mirror_with_compact_lv_and_underscore_continuations(self):
        try:
            executable = renderer_executable()
        except ValueError:
            self.skipTest('SILE is needed for the layout integration check')
        root = ET.Element('sile', {'class': 'oet', 'papersize': 'b5'})
        book = ET.SubElement(root, 'book', {'name': 'Fixture', 'code': 'MRK', 'version': 'DEMO',
            'sides': 'rv lv', 'primary-column': 'outside', 'primary-width': '0.53',
            'rv-font-size': '10.4', 'lv-font-size': '9.4', 'lv-line-spacing': '11.25',
            'rv-line-breaks': 'english', 'lv-line-breaks': 'underscore',
            'edition-title': 'Fixture', 'rv-label': 'Readers', 'lv-label': 'Literal'})
        ET.SubElement(ET.SubElement(book, 'intro', kind='ip'), 'run').text = 'Full width introduction.'
        for verse in range(1, 9):
            section = ET.SubElement(book, 'section')
            ET.SubElement(ET.SubElement(section, 'heading'), 'run').text = f'Heading{verse:03}'
            for side in ('rv', 'lv'):
                block = ET.SubElement(ET.SubElement(section, side), 'block',
                                      ref=f'1:{verse}', verse=str(verse), para='p')
                words = 'demonstration of extraordinary circumstances ' if side == 'rv' else 'alpha_beta_gamma_delta_epsilon_zeta '
                ET.SubElement(block, 'run').text = f'{side.upper()}{verse:03} ' + words * 12
                if side == 'lv':
                    ET.SubElement(block, 'run').text = ' ' + 'repeat_' * 20 + f'Tail{verse:03}'
                    note = ET.SubElement(block, 'note', edition='LV', ref=f'1:{verse}', kind='Note')
                    ET.SubElement(note, 'run').text = f'Note{verse:03} a footnote after a repeatedly broken word.'
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            render_sile(directory, root, executable)
            xml = subprocess.check_output(['pdftotext', '-bbox', str(directory / 'proof.pdf'), '-'])
        anchors, underscored, hyphenated = {}, 0, 0
        notes, tails = {}, {}
        for page_no, page in enumerate(ET.fromstring(xml).findall('.//{*}page'), 1):
            for word in page.findall('.//{*}word'):
                text = word.text or ''
                if len(text) == 5 and text[:2] in ('RV', 'LV') and text[2:].isdigit():
                    anchors[text] = (page_no, float(word.get('yMin')), float(word.get('xMin')))
                    outside = float(word.get('xMin')) > float(page.get('width')) / 2 if page_no % 2 else float(word.get('xMin')) < float(page.get('width')) / 2
                    self.assertEqual(outside, text.startswith('RV'))
                if text.startswith('Note') and text[4:].isdigit(): notes[int(text[4:])] = page_no
                if 'Tail' in text and text[-3:].isdigit(): tails[int(text[-3:])] = page_no
                underscored += text.startswith('_')
                hyphenated += text.endswith('-')
        self.assertEqual(len(anchors), 16)
        self.assertEqual(notes, tails)
        self.assertEqual(len(notes), 8)
        for verse in range(1, 9):
            rv, lv = anchors[f'RV{verse:03}'], anchors[f'LV{verse:03}']
            self.assertEqual(rv[0], lv[0])
            # Glyph tops differ slightly with font size, but baselines align.
            self.assertLess(abs(rv[1] - lv[1]), 1.5)
        self.assertGreater(underscored, 8)
        self.assertGreater(hyphenated, 2)


if __name__ == '__main__':
    unittest.main()
