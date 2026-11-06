"""Shared print/screen conversion, including source links and safe URI handling."""
import argparse
import unittest
import xml.etree.ElementTree as ET

from oet_publication import linked_runs, link_publication, output_arguments, reading_url
from SILE.typeset import content


class PublicationLinkTests(unittest.TestCase):
    def test_cli_defaults_and_mutual_exclusion(self):
        parser = argparse.ArgumentParser(exit_on_error=False)
        output_arguments(parser)
        self.assertEqual(parser.parse_args([]).medium, 'print')
        self.assertEqual(parser.parse_args(['--print']).medium, 'print')
        self.assertEqual(parser.parse_args(['--screen']).medium, 'screen')
        with self.assertRaises(argparse.ArgumentError):
            parser.parse_args(['--print', '--screen'])

    def test_url_display_and_punctuation_do_not_change_destinations(self):
        text = 'Visit OET.Bible, or (https://example.org/a_(b)?q=x+y&n=1#Top).'
        targets = ['https://OET.Bible', 'https://example.org/a_(b)?q=x+y&n=1#Top']
        for medium in ('print', 'screen'):
            runs = linked_runs(text, medium, {'style': 'it'})
            self.assertEqual([r.get('href') for r in runs if r.get('href')], targets)
            self.assertTrue(all(r.get('style') == 'it' for r in runs))
            visible = ''.join(r.text for r in runs)
            self.assertTrue(visible.endswith('#Top).'))
            self.assertEqual(visible.count('https://'), 2 if medium == 'print' else 0)

    def test_explicit_source_links_survive_styles_and_resolve_online(self):
        node = ET.Element('intro')
        content(node, r'See \it \jmp later|link-href="#C12V3"\jmp*\it* and '
                r'\jmp Song 25|link-href="../byC/PSA_C25.htm#Top"\jmp*.', '', 'RV')
        link_publication(node, 'screen', reading_url('JHN'))
        links = node.findall('run[@href]')
        self.assertEqual([r.text for r in links], ['later', 'Song 25'])
        self.assertEqual(links[0].get('style'), 'it')
        self.assertEqual(links[0].get('href'), 'https://Freely-Given.org/OBD/OET/byDoc/JHN.htm#C12V3')
        self.assertEqual(links[1].get('href'), 'https://Freely-Given.org/OBD/OET/byC/PSA_C25.htm#Top')
        print_runs = linked_runs('later', 'print', {'href': '#C12V3'}, reading_url('JHN'))
        self.assertEqual(print_runs[0].text, 'later (https://Freely-Given.org/OBD/OET/byDoc/JHN.htm#C12V3)')

    def test_lv_joins_do_not_corrupt_url_queries_or_destinations(self):
        node = ET.Element('block')
        content(node, 'some+word=part https://example.org/?a=b+c.', '1:1', 'LV')
        link_publication(node, 'screen')
        self.assertEqual(''.join(node.itertext()), 'some_word_part example.org/?a=b+c.')
        self.assertEqual(node.find('run[@href]').get('href'), 'https://example.org/?a=b+c')

    def test_non_web_actions_are_not_activated(self):
        runs = linked_runs('unsafe action', 'screen', {'href': 'javascript:alert(1)'})
        self.assertIsNone(runs[0].get('href'))


if __name__ == '__main__':
    unittest.main()
