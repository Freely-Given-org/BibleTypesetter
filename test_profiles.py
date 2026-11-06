"""Publication data isolation, inheritance, source discovery and artwork settings."""
import argparse
from pathlib import Path
import struct
import tempfile
import unittest

from publication_config import load_profile, resolve_arguments
from oet_books import selection_arguments, select_books
from SILE.typeset import selected_content


NEUTRAL = '''page_numbers = "centred"
[publication]
id = "DEMO"
title = "Example Bible\\nTest Edition"
default_version = "DEMO"
author = "Example Publisher"
licence = "Public-domain fixture"
intro_licence = "{licence}"
draft_template = "Example draft {version} · example.org"
draft_version = "v2.1"
copyright_paragraphs = ["{draft_credit}", "{licence}"]
reading_url = "https://example.org/{code}"
collection_url = "https://example.org/"
[editions.DEMO]
sides = ["rv", "lv"]
label = "Parallel example"
[editions.SOLO]
sides = ["rv"]
label = "Single example"
[sources]
root = "texts"
[sources.rv]
id = "ALPHA"
label = "First version"
patterns = ["left/{code}.usfm"]
[sources.lv]
id = "BETA"
label = "Second version"
patterns = ["right/{code}.usfm"]
[books]
default = ["MRK"]
[screen_colours]
link = "123456"
'''


class ProfileTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.config = self.root / 'publication.toml'
        self.config.write_text(NEUTRAL)
        for side in ('left', 'right'):
            source = self.root / f'texts/{side}/MRK.usfm'
            source.parent.mkdir(parents=True)
            source.write_text('\\id MRK v1.2.3\n\\h Example\n\\mt1 Example\n\\c 1\n\\v 1 Text a+b=c.\n')

    def args(self, version=None):
        parser = argparse.ArgumentParser()
        selection_arguments(parser)
        args = parser.parse_args([])
        args.layout_settings = self.config
        args.version, args.oet_root, args.medium = version, None, 'screen'
        resolve_arguments(args)
        return args

    def test_custom_publication_never_uses_default_translation_data(self):
        args = self.args()
        books, front = selected_content(args, select_books(args), 'Toolchain test')
        self.assertIsNone(front)
        book = books[0]
        self.assertEqual(book.get('opening-title'), 'Example Bible\nTest Edition')
        self.assertEqual(book.get('rv-colophon'), 'MRK · ALPHA v1.2.3')
        self.assertEqual(book.get('lv-colophon'), 'MRK · BETA v1.2.3')
        self.assertIn('Public-domain fixture', ''.join(book.itertext()))
        self.assertEqual(''.join(book.find('section/lv/block').itertext()), 'Text a+b=c.')
        self.assertEqual(book.find('reading-link/run').get('href'), 'https://example.org/MRK')
        self.assertEqual(book.get('colour-link'), '123456')
        self.assertFalse(any('logo-' in k for k in book.attrib))
        self.assertNotIn('OET', str(book.attrib) + ''.join(book.itertext()))

    def test_single_version_and_front_matter_need_no_second_source_or_preface(self):
        (self.root / 'texts/right/MRK.usfm').unlink()
        args = self.args('solo')
        args.front_matter = True
        books, front = selected_content(args, select_books(args), 'Toolchain test')
        self.assertEqual(args.version, 'SOLO')
        self.assertEqual(books[0].get('sides'), 'rv')
        self.assertIsNone(books[0].find('.//lv'))
        self.assertIsNone(front.find('preface'))
        self.assertEqual(front.get('fulltitle'), 'Example Bible\nTest Edition')

    def test_inheritance_resolves_paths_where_declared_and_merges_tables(self):
        child_dir = self.root / 'engine'
        child_dir.mkdir()
        child = child_dir / 'settings.toml'
        child.write_text('extends = "../publication.toml"\npage_numbers = "outside"\n'
                         '[publication]\nauthor = "Override Publisher"\n')
        profile = load_profile(child)
        self.assertEqual(profile.source_root, self.root / 'texts')
        self.assertEqual(profile.publication['author'], 'Override Publisher')
        self.assertEqual(profile.title, 'Example Bible\nTest Edition')
        self.assertEqual(profile.page_numbers, 'outside')

    def test_inheritance_cycle_reports_a_clear_error(self):
        self.config.write_text('extends = "child.toml"\n')
        (self.root / 'child.toml').write_text('extends = "publication.toml"\n')
        with self.assertRaisesRegex(ValueError, 'cyclic'):
            load_profile(self.config)

    def test_logo_variants_keep_aspect_ratio_and_can_be_disabled(self):
        # Only metadata is read here; renderer tests exercise the complete PNG.
        for name, w, h in [('colour', 400, 100), ('black', 200, 100)]:
            (self.root / f'{name}.png').write_bytes(b'\x89PNG\r\n\x1a\n' + b'\0'*8 + struct.pack('>II', w, h))
        self.config.write_text(NEUTRAL + '''
[logos.opening]
enabled = true
screen = "colour.png"
print = "black.png"
height_pt = 30
max_width_pt = 90
href = "https://example.org/"
[logos.footer]
enabled = false
''')
        profile = load_profile(self.config)
        screen = profile.logo_attributes('screen')
        paper = profile.logo_attributes('print')
        self.assertEqual(float(screen['logo-opening-width']), 90)
        self.assertEqual(float(screen['logo-opening-height']), 22.5)
        self.assertEqual(float(paper['logo-opening-width']), 60)
        self.assertEqual(float(paper['logo-opening-height']), 30)
        self.assertNotIn('logo-footer-src', screen)
        self.assertEqual(screen['logo-opening-src'], str(self.root / 'colour.png'))

    def test_bad_profile_fields_fail_before_rendering(self):
        for change, pattern in [
                (NEUTRAL.replace('centred', 'diagonal'), 'page_numbers'),
                (NEUTRAL.replace('"123456"', '"purple"'), 'six hexadecimal'),
                (NEUTRAL.replace('left/{code}.usfm', 'left/book.usfm'), 'source patterns'),
                (NEUTRAL.replace('sides = ["rv", "lv"]', 'sides = ["third"]'), 'sides must')]:
            with self.subTest(pattern=pattern):
                self.config.write_text(change)
                with self.assertRaisesRegex(ValueError, pattern):
                    load_profile(self.config)


if __name__ == '__main__':
    unittest.main()
