"""Batch correctness: dependency changes, missing files and failed replacements."""
import argparse
from contextlib import ExitStack, redirect_stdout, redirect_stderr
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from SILE import build_pdfs as batch
from SILE.download_page import download_page
from publication_config import load_profile


class BatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_catalogue_includes_every_book_once_and_uses_aliases(self):
        profile = load_profile(Path(__file__).parent / 'settings.toml')
        targets = batch.catalogue(profile, profile.version)
        by_key = {t.key: t for t in targets}
        self.assertEqual(len(targets), 88)
        self.assertEqual([len(by_key[g].selection.codes) for g in ('OT', 'NT', 'DC', 'ALL')], [39, 27, 18, 84])
        self.assertEqual(len({t.key for t in targets}), 88)
        self.assertEqual({t.key for t in targets if not t.selection.collection}, set(by_key['ALL'].selection.codes))
        self.assertEqual(by_key['LAO'].group, 'DC')
        self.assertIn('other', by_key['DC'].selection.title)
        self.assertTrue(any(p.name == 'OET-RV_ES2.ESFM' for p in by_key['LES'].sources))
        self.assertTrue(any(p.name == 'OET-RV_FRT.ESFM' for p in by_key['NT'].sources))
        self.assertFalse(any(p.name == 'OET-RV_FRT.ESFM' for p in by_key['RUT'].sources))

    def test_default_matrix_and_rv_membership(self):
        profile = load_profile(Path(__file__).parent / 'settings.toml')
        args = argparse.Namespace(version=None, paper_size=None)
        matrix = batch.variants(profile, args)
        self.assertEqual(len(matrix), 8)
        for version in ('OET', 'OET-RV'):
            self.assertEqual([(medium, size) for v, medium, size in matrix if v == version],
                             [('print', 'b5'), ('print', 'a4'), ('print', 'letter'), ('screen', 'b5')])
        targets = batch.catalogue(profile, 'OET-RV')
        self.assertEqual(len(targets), 86)
        self.assertFalse(any(t.key in ('PSS', 'ODE') for t in targets))
        self.assertTrue(all(not any('OET-LV' in p.name for p in t.sources) for t in targets))
        args.version, args.paper_size = 'OET-RV', 'Letter'
        self.assertEqual(batch.variants(profile, args), [('OET-RV', 'print', 'letter'), ('OET-RV', 'screen', 'letter')])

    def test_fingerprint_is_independent_of_relative_script_invocation(self):
        profile = load_profile(Path(__file__).parent / 'settings.toml')
        absolute = batch.common_inputs(profile, batch.renderer_executable(), 'print')
        with patch.object(batch, '__file__', '/srv/FreelyGiven/OpenEnglishTranslation--OET/scripts/../../BibleTypesetter/SILE/build_pdfs.py'):
            relative = batch.common_inputs(profile, batch.renderer_executable(), 'print')
        self.assertEqual(absolute, relative)

    def test_content_hashes_detect_same_mtime_changes_and_missing_outputs(self):
        pdf = self.root / 'proof.pdf'
        pdf.write_bytes(b'first proof')
        record = {'fingerprint': 'inputs-v1', 'bytes': pdf.stat().st_size, 'sha256': batch.digest(pdf)}
        self.assertTrue(batch.current(record, 'inputs-v1', pdf))
        self.assertFalse(batch.current(record, 'inputs-v2', pdf))
        pdf.write_bytes(b'other proof')
        self.assertFalse(batch.current(record, 'inputs-v1', pdf))
        pdf.unlink()
        self.assertFalse(batch.current(record, 'inputs-v1', pdf))

    def test_unchanged_manifest_preserves_timestamp(self):
        manifest = self.root / 'manifest.json'
        batch.atomic_json(manifest, {'entries': ['RUT']})
        stamp = manifest.stat().st_mtime_ns
        batch.atomic_json(manifest, {'entries': ['RUT']})
        self.assertEqual(manifest.stat().st_mtime_ns, stamp)
        batch.atomic_json(manifest, {'entries': ['MRK']})
        self.assertIn('MRK', manifest.read_text())

    def test_download_page_labels_include_codes_and_escape_source_names(self):
        file = {'url': 'https://example.org/NUM.pdf', 'bytes': 1234, 'pages': 10, 'medium': 'print', 'paper_size': 'A4'}
        catalogue = {'title': 'Bible', 'draft_version': 'v1', 'paper_size': 'B5',
            'groups': [{'id': 'OT', 'title': 'Old Testament'}],
            'editions': [{'id': 'OET-RV', 'label': 'Readers’ Version', 'entries': [{'id': 'NUM', 'kind': 'book', 'group': 'OT', 'title': 'Census', 'files': [file]},
                        {'id': 'JDG', 'kind': 'book', 'group': 'OT', 'title': 'Heroes and Guides', 'files': [file]}]}]}
        page = download_page(catalogue, {})
        self.assertIn('<th scope="row">Census (NUM)</th>', page)
        self.assertIn('<th scope="row">Heroes and Guides (JDG)</th>', page)
        self.assertIn('aria-label="Census (NUM) — Readers’ Version — Print A4 PDF"', page)
        catalogue['editions'][0]['entries'][0]['title'] = '<not markup>'
        self.assertIn('&lt;not markup&gt; (NUM)', download_page(catalogue, {}))

    def test_source_change_invalidates_only_relevant_book_and_collections(self):
        profile = load_profile(Path(__file__).parent / 'settings.toml')
        targets = batch.catalogue(profile, profile.version)
        affected = [t.key for t in targets if any(p.name == 'OET-RV_RUT.ESFM' for p in t.sources)]
        self.assertEqual(set(affected), {'RUT', 'OT', 'ALL'})
        affected = [t.key for t in targets if any(p.name == 'OET-LV_LAO.ESFM' for p in t.sources)]
        self.assertEqual(set(affected), {'LAO', 'DC', 'ALL'})

    def test_failed_render_or_validation_preserves_previous_pdf(self):
        proof = self.root / 'proof.pdf'
        proof.write_bytes(b'previous good PDF')
        args = argparse.Namespace(layout_settings=self.root / 'config.toml', version='EXAMPLE',
                                  paper_size='b5', sile='sile')
        chosen = argparse.Namespace(collection=None, draft_version='v1')
        target = batch.Target('RUT', 'Ruth', 'OT', chosen, [])
        def fake_render(command, **kwargs):
            Path(command[command.index('-o') + 1]).write_bytes(b'new incomplete PDF')
            return argparse.Namespace(returncode=1)
        with patch.object(batch.subprocess, 'run', side_effect=fake_render):
            with self.assertRaisesRegex(ValueError, 'build failed'):
                batch.build_one(target, 'print', args, 'hash', proof, self.root / 'build.log')
        self.assertEqual(proof.read_bytes(), b'previous good PDF')

        def successful_process(command, **kwargs):
            fake_render(command, **kwargs)
            return argparse.Namespace(returncode=0)
        with patch.object(batch.subprocess, 'run', side_effect=successful_process), patch.object(batch, 'pdf_pages', side_effect=ValueError('invalid PDF')):
            with self.assertRaisesRegex(ValueError, 'invalid PDF'):
                batch.build_one(target, 'print', args, 'hash', proof, self.root / 'build.log')
        self.assertEqual(proof.read_bytes(), b'previous good PDF')

    def test_batch_skips_unchanged_files_repairs_deletions_and_retains_manifest_on_failure(self):
        config = self.root / 'profile.toml'
        config.write_text('''[publication]
id="DEMO"
title="Demo Bible"
default_version="DEMO"
[editions.DEMO]
sides=["rv"]
[sources]
root="."
[sources.rv]
id="DEMO"
patterns=["{code}.usfm"]
''')
        rut, mrk = self.root / 'RUT.usfm', self.root / 'MRK.usfm'
        rut.write_text('Ruth version 1')
        mrk.write_text('Mark version 1')
        def target(code, books, files, group, collection=None):
            chosen = argparse.Namespace(collection=collection, order='traditional',
                codes=books, draft_version='v1', stem=code)
            return batch.Target(code, code, group, chosen, files)
        targets = [target('ALL', ['RUT', 'MRK'], [rut, mrk], 'ALL', 'ALL'),
                   target('RUT', ['RUT'], [rut], 'OT'), target('MRK', ['MRK'], [mrk], 'NT')]
        args = argparse.Namespace(layout_settings=config, output_dir=self.root / 'public',
            cache_dir=self.root / 'cache', catalogue_file=self.root / 'site/data/pdfs.json', version=None, paper_size=None, only=None,
            jobs=2, sile=None, force=False, list_targets=False)
        calls, fail = [], set()
        def fake_build(target, medium, args, fingerprint, destination, log):
            calls.append((target.key, medium))
            if target.key in fail:
                raise ValueError('render failed')
            destination.write_bytes(fingerprint.encode())
            return {'fingerprint': fingerprint, 'filename': destination.name,
                    'bytes': destination.stat().st_size, 'sha256': batch.digest(destination),
                    'pages': 1, 'draft_version': 'v1'}
        with ExitStack() as stack:
            stack.enter_context(redirect_stdout(io.StringIO()))
            stack.enter_context(redirect_stderr(io.StringIO()))
            stack.enter_context(patch.object(batch, 'catalogue', return_value=targets))
            stack.enter_context(patch.object(batch, 'renderer_executable', return_value='sile'))
            stack.enter_context(patch.object(batch, 'require_poppler'))
            stack.enter_context(patch.object(batch, 'common_inputs', return_value={'code': 'v1'}))
            stack.enter_context(patch.object(batch, 'build_one', side_effect=fake_build))
            batch.run(args)
            self.assertEqual(len(calls), 6)
            manifest = args.output_dir / 'manifest.json'
            self.assertEqual(args.catalogue_file.read_bytes(), manifest.read_bytes())
            stamp = manifest.stat().st_mtime_ns
            calls.clear()
            batch.run(args)
            self.assertEqual(calls, [])
            self.assertEqual(manifest.stat().st_mtime_ns, stamp)
            rut.write_text('Ruth version 2')
            batch.run(args)
            self.assertEqual(set(calls), {('RUT', 'print'), ('RUT', 'screen'), ('ALL', 'print'), ('ALL', 'screen')})
            calls.clear()
            (args.output_dir / 'DEMO-MRK.B5.screen.pdf').unlink()
            batch.run(args)
            self.assertEqual(calls, [('MRK', 'screen')])
            previous = manifest.read_bytes()
            rut.write_text('Ruth version 3')
            fail.add('RUT')
            with self.assertRaisesRegex(ValueError, 'previous download manifest retained'):
                batch.run(args)
            self.assertEqual(manifest.read_bytes(), previous)
            calls.clear()
            fail.clear()
            batch.run(args)
            self.assertEqual(set(calls), {('RUT', 'print'), ('RUT', 'screen')})


if __name__ == '__main__':
    unittest.main()
