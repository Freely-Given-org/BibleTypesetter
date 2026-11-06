"""Collection, front matter and cross-edition alignment regression checks."""
import argparse
import json
from pathlib import Path
import tempfile
import unittest

from oet_books import NT, OT, SETTINGS, read_orders, selection_arguments, select_books, source_path
from SILE.typeset import OET, paired_book, publication_front, read_edition, selected_content, paper_size
from oet_publication import PRINT_TITLE, default_pdf_filename


class CollectionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.settings = self.root / 'settings.py'
        self.settings.write_text('raise RuntimeError("must never execute website settings")\n'
            'class State:\n'
            f'    OET_OT_BOOK_ORDER = {OT!r}\n'
            f'    OET_NT_BOOK_ORDER = {list(reversed(NT))!r}\n'
            "    OET_APOCRYPHA_BOOK_ORDER = ['PS2', 'GES', 'LES', 'PSS']\n"
            "    OET_RV_DC_BOOK_LIST = ['PS2', 'GES', 'LES', 'LAO']\n"
            "    OET_LV_DC_BOOK_LIST = ['PS2', 'GES', 'PSS', 'LAO']\n"
            "    OET_SOURCE_BOOK_ALIASES = {'ES1': 'GES', 'ES2': 'LES', 'DAG': 'DNG'}\n"
            '    OET_BOOK_ORDER = OET_OT_BOOK_ORDER + OET_APOCRYPHA_BOOK_ORDER + OET_NT_BOOK_ORDER\n'
            "    OET_BOOK_ORDER.insert(OET_BOOK_ORDER.index('COL')+1, 'LAO')\n")
        self.parser = argparse.ArgumentParser()
        selection_arguments(self.parser)
        self.parser.add_argument('--version', default='OET')

    def select(self, *args):
        return select_books(self.parser.parse_args(['--settings', str(self.settings), *args]))

    def test_collection_membership_and_orders(self):
        for version, dc_count in [('OET', 5), ('OET-RV', 4), ('OET-LV', 4)]:
            for order in ['oet', 'traditional']:
                for collection, count in [('OT', 39), ('NT', 27), ('DC', dc_count), ('ALL', 66 + dc_count)]:
                    with self.subTest(version=version, order=order, collection=collection):
                        result = self.select(collection, '--version', version, '--book-order', order)
                        self.assertTrue(result.front)
                        self.assertEqual(len(result.codes), count)
                        self.assertEqual(len(set(result.codes)), count)
        self.assertEqual(self.select('NT').codes, list(reversed(NT)))
        self.assertEqual(self.select('NT', '--book-order', 'traditional').codes, NT)
        all_books = self.select('ALL').codes
        self.assertEqual(all_books[all_books.index('COL')+1], 'LAO')
        self.assertEqual(self.select('DC', '--book-order', 'traditional').codes,
                         ['GES', 'LES', 'PS2', 'PSS', 'LAO'])

    def test_explicit_books_aliases_and_invalid_combinations(self):
        self.assertEqual(self.select('ES1', 'MRK').codes, ['GES', 'MRK'])
        self.assertFalse(self.select('MRK').front)
        self.assertTrue(self.select('MRK', '--front-matter').front)
        for args in [('ES1', 'GES'), ('OT', '--collection', 'NT'), ('MRK', '--collection', 'NT')]:
            with self.subTest(args=args), self.assertRaises(ValueError):
                self.select(*args)

    def test_settings_are_read_without_executing_python(self):
        self.assertEqual(read_orders(self.settings)['OET_SOURCE_BOOK_ALIASES']['ES1'], 'GES')
        self.settings.write_text(self.settings.read_text().replace("['PS2', 'GES', 'LES', 'PSS']", "dangerous_function()"))
        with self.assertRaisesRegex(ValueError, 'unsupported book-order expression'):
            read_orders(self.settings)

    def test_draft_and_book_versions_come_from_their_own_sources(self):
        with self.settings.open('a') as settings:
            settings.write("    OET_VERSION_NUMBER_STRING = 'v9.8.7'\n")
        path = self.source('MRK', 'RV', '\\c 1\n\\v 1 Text with v99.0 in the body.')
        path.write_text(path.read_text().replace('\\id MRK\n', '\\id MRK OET-RV v1.2.3-beta\n'))
        self.source('MRK', 'LV', '\\c 1\n\\v 1 Literal text.')
        self.source('FRT', 'RV', '\\periph Preface\n\\p Preface text.')
        args = self.parser.parse_args(['MRK', '--settings', str(self.settings), '--front-matter'])
        args.oet_root = self.root
        self.assertFalse(args.start_books_on_odd_pages)
        selection = select_books(args)
        books, front = selected_content(args, selection)
        self.assertEqual(selection.draft_version, 'v9.8.7')
        self.assertIn('Translation draft v9.8.7 · OET.Bible', books[0].get('draft-credit'))
        self.assertEqual(books[0].get('rv-colophon'), 'MRK · OET-RV v1.2.3-beta')
        self.assertIn('version not specified in source ID', books[0].get('lv-colophon'))
        self.assertEqual(books[0].get('recto'), 'false')
        args.start_books_on_odd_pages = True
        self.assertEqual(selected_content(args, selection)[0][0].get('recto'), 'true')
        self.assertEqual(front.get('fulltitle'), PRINT_TITLE)
        self.assertIn('Translation draft v9.8.7', ''.join(front.find('copyright').itertext()))
        self.assertIn('CC BY-SA 4.0', ''.join(front.find('copyright').itertext()))

    def test_missing_version_setting_is_not_fabricated(self):
        self.assertIsNone(self.select('NT').draft_version)
        with self.settings.open('a') as settings:
            settings.write('    OET_VERSION_NUMBER_STRING = 42\n')
        with self.assertRaisesRegex(ValueError, 'must be a string'):
            self.select('NT')

    def test_title_and_toolchain_are_placed_once_for_the_whole_selection(self):
        for code in ['JN2', 'JN3']:
            self.source(code, 'RV', '\\c 1\n\\v 1 Text.')
        self.source('FRT', 'RV', '\\periph Preface\n\\p Preface text.')
        args = self.parser.parse_args(['JN2', 'JN3', '--settings', str(self.settings), '--version', 'OET-RV'])
        args.oet_root = self.root
        credit = 'Text preprocessed by script v1.0.0, then PDF produced by Example v2.0.1'
        books, front = selected_content(args, select_books(args), credit)
        self.assertIsNone(front)
        self.assertEqual([b.get('opening-title') for b in books], [PRINT_TITLE, None])
        self.assertEqual([b.get('toolchain') for b in books], [None, credit])
        args.front_matter = True
        books, front = selected_content(args, select_books(args), credit)
        self.assertTrue(all(b.get('opening-title') is None and b.get('toolchain') is None for b in books))
        self.assertEqual([node.text for node in front.findall('copyright/intro[@kind="toolchain"]/run')], [credit])

    def test_lv_release_comes_from_each_books_own_folder(self):
        derived = self.root / 'derivedTexts'
        derived.mkdir()
        (derived / 'version.json').write_text('{"group": "names", "version": "v9.9.9"}')
        for code, folder, group, version in [
                ('RUT', 'auto_edited_OT_ESFM', 'OT', 'v1.0.0'),
                ('MRK', 'auto_edited_VLT_ESFM', 'NT', 'v2.0.0'),
                ('TOB', 'auto_edited_DC_ESFM', 'DC', 'v3.0.0'),
                ('LAO', 'other_books', 'Other', 'v4.0.0')]:
            with self.subTest(code=code):
                directory = derived / folder
                directory.mkdir()
                source = directory / f'OET-LV_{code}.ESFM'
                source.write_text(f'\\id {code} v0.1.1\n\\h {code}\n\\mt1 {code}\n\\c 1\n\\v 1 Text.')
                (directory / 'version.json').write_text(json.dumps(
                    {'resource': 'OET-LV', 'group': group, 'version': version,
                     'build_inputs': {'tools': {'example': {'version': '8.8.8'}}}}))
                book = paired_book(self.root, code, 'OET-LV')
                self.assertEqual(book.get('lv-colophon'),
                                 f'{code} · OET-LV {version} ({group} set) · book v0.1.1')

    def test_paper_size_is_preserved_in_default_filenames(self):
        for size, suffix in [('B5', 'B5'), ('A4', 'A4'), ('letter', 'Letter'),
                             ('160x240mm', '160x240mm'), ('6 x 9 inches', '6x9in'),
                             ('8.5in x 297mm', '8.5inx297mm')]:
            self.assertEqual(default_pdf_filename('OET', 'NT-oet', paper_size(size)),
                             f'OET-NT-oet.{suffix}.print.pdf')
            self.assertEqual(default_pdf_filename('OET', 'NT-oet', paper_size(size), 'screen'),
                             f'OET-NT-oet.{suffix}.screen.pdf')

    def source(self, code, edition, text):
        directory = 'translatedTexts/ReadersVersion' if edition == 'RV' else 'derivedTexts/auto_edited_VLT_ESFM'
        path = self.root / directory / f'OET-{edition}_{code}.ESFM'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f'\\id {code}\n\\h {code}\n\\mt1 {code}\n{text}\n')
        return path

    def test_source_alias_is_unique(self):
        path = self.source('ES1', 'RV', '\\c 1\n\\v 1 Text.')
        aliases = {'ES1': 'GES'}
        self.assertEqual(source_path(self.root, 'RV', 'GES', aliases), path)
        self.source('GES', 'RV', '\\c 1\n\\v 1 Duplicate.')
        with self.assertRaisesRegex(ValueError, 'found 2'):
            source_path(self.root, 'RV', 'GES', aliases)

    def test_chapter_pairing_preserves_source_order_and_missing_versions(self):
        self.source('PSS', 'LV', '\\c 1\n\\v 2 Second.\n\\v 1 First.\n\\c 2\n\\v 1 Next.')
        book = paired_book(self.root, 'PSS', chapter_pair=True)
        self.assertIn('chapter only', ''.join(book.find('intro').itertext()))
        self.assertEqual(len(book.findall('section')), 2)
        self.assertEqual([b.get('verse') for b in book.find('section/lv')], ['2', '1'])
        self.assertIn('No RV source text', ''.join(book.find('section/rv').itertext()))
        self.assertIn('source unavailable', book.get('rv-colophon'))
        self.assertIn('version not specified in source ID', book.get('lv-colophon'))

    def test_headings_within_a_chapter_are_kept_with_their_own_text(self):
        self.source('LAO', 'RV', '\\c 1\n\\s1 First\n\\v 1 One.\n\\s1 Second\n\\v 3 Three.')
        self.source('LAO', 'LV', '\\c 1\n\\v 1 Different.\n\\v 2 Numbering.')
        book = paired_book(self.root, 'LAO', chapter_pair=True)
        self.assertEqual([b.tag for b in book.find('section/rv')], ['heading', 'block', 'heading', 'block'])
        self.assertEqual(len(book.findall('section')), 1)

    def test_preface_uses_only_the_complete_preface_peripheral(self):
        self.source('FRT', 'RV', '\\periph Title Page\n\\p Not the preface.\n'
                    '\\periph Preface\n\\mt1 Preface\n\\p Beginning.\n\\li2 Last \\em words\\em*.\n'
                    '\\periph Other\n\\p Not included.')
        front = publication_front(self.root, self.select('NT'), 'OET-LV', [])
        self.assertEqual(''.join(front.find('preface').itertext()), 'PrefaceBeginning.Last words.')
        self.assertEqual(front.find('preface')[-1].get('kind'), 'li2')
        self.assertEqual(front.find('entry').get('code'), 'FRT')

    def test_midverse_paragraph_is_not_lost_at_a_heading(self):
        path = self.source('MRK', 'RV', '\\c 1\n\\v 1 Before.\n\\s1 Heading\n\\p Continuation.\n\\v 2 After.')
        book = read_edition(path, 'RV')
        self.assertEqual(''.join(''.join(b.itertext()) for _, b in book.blocks), 'Before.Continuation.After.')
        self.assertEqual(book.blocks[1][0], (1, 2, ''))

    @unittest.skipUnless(SETTINGS.is_file() and OET.is_dir(), 'live OET checkouts unavailable')
    def test_live_membership_and_versification(self):
        args = self.parser.parse_args(['ALL', '--settings', str(SETTINGS)])
        for version, count in [('OET', 84), ('OET-RV', 82), ('OET-LV', 83)]:
            args.version = version
            self.assertEqual(len(select_books(args).codes), count)
        for code in ['PSA', 'NEH', 'ACT']:
            book = paired_book(OET, code)
            for section in book.findall('section'):
                self.assertTrue(len(section.find('rv')))
                self.assertTrue(len(section.find('lv')))
        neh = paired_book(OET, 'NEH')
        self.assertIn('No LV counterpart for RV 7:68.', ''.join(neh.itertext()))


if __name__ == '__main__':
    unittest.main()
