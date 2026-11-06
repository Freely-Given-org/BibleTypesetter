#!/usr/bin/env python3
"""Incrementally build a website's collection and individual-book SILE PDFs.

Publication data, output locations and batch defaults come from TOML. Run
without --only to build every configured edition and print/screen paper size.
Only a successful full batch replaces the public download manifest.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from urllib.parse import urlsplit

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from oet_books import select_books, source_path
from oet_publication import PREPROCESSOR_VERSION, default_pdf_filename, pdf_pages, require_poppler
from publication_config import load_profile, profile_arguments
from SILE.typeset import clean, inline, mapping_engine, paper_size
from SILE.download_page import download_page
import xml.etree.ElementTree as ET


@dataclass
class Target:
    key: str
    title: str
    group: str
    selection: object
    sources: list


def selection(profile, version, codes, order=None, root=None):
    return select_books(argparse.Namespace(
        books=codes, collection=None, settings=profile.settings_file,
        profile=profile, version=version, book_order=order, front_matter=False,
        oet_root=root or profile.source_root))


def catalogue(profile, version):
    batch = profile.data.get('batch', {})
    groups = batch.get('collections', ['OT', 'NT', 'DC', 'ALL'])
    if set(groups) != {'OT', 'NT', 'DC', 'ALL'} or len(groups) != 4:
        raise ValueError('batch.collections must contain OT, NT, DC and ALL once each')
    order = profile.data.get('books', {}).get('collection_order', 'traditional')
    selections = {g: selection(profile, version, [g], order) for g in groups}
    sides = profile.sides(version)
    sources, titles = {}, {}
    for code in selections['ALL'].codes:
        paths = []
        for side in sides:
            path = source_path(profile.source_root, side, code, selections['ALL'].aliases,
                               required=code not in selections['ALL'].dc, profile=profile)
            if path is None:
                continue
            paths.append(path)
            # Prefer the first source's human-readable book name, as the renderer does.
            if code not in titles:
                for line in path.read_text(encoding='utf-8-sig').splitlines():
                    if line.startswith('\\h '):
                        name = ET.Element('name')
                        inline(name, clean(line[3:], profile), side, profile)
                        titles[code] = ''.join(name.itertext())
                        break
            release = profile.source(side).get('release_file')
            if release:
                paths.append(path.parent / release)  # Include absence in the fingerprint.
        if not paths:
            raise ValueError(f'{code}: neither configured source is available')
        sources[code] = paths
    targets = []
    labels = batch.get('group_labels', {})
    for group in groups:
        chosen = selections[group]
        paths = [p for code in chosen.codes for p in sources[code]]
        preface = profile.data.get('preface', {})
        if preface:
            paths.append(source_path(profile.source_root, preface.get('source_side', 'rv'),
                                     preface['code'], chosen.aliases, profile=profile))
        targets.append(Target(group, labels.get(group, chosen.title), group, chosen, paths))
    for code in selections['ALL'].codes:
        group = next(g for g in groups if g != 'ALL' and code in selections[g].codes)
        targets.append(Target(code, titles.get(code, code), group,
                              selection(profile, version, [code]), sources[code]))
    return targets


def digest(path):
    if not path.is_file():
        return None
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def signature(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def atomic_bytes(path, content):
    """Keep unchanged bytes/mtime, and never expose a partial JSON document."""
    if path.is_file() and path.read_bytes() == content:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.' + path.name, dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(content)
        os.chmod(temporary, 0o644)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def atomic_json(path, value):
    atomic_bytes(path, (json.dumps(value, indent=2, ensure_ascii=False) + '\n').encode())


def current(record, fingerprint, path):
    return bool(record and record.get('fingerprint') == fingerprint and path.is_file()
                and path.stat().st_size == record['bytes'] and digest(path) == record['sha256'])


def renderer_executable(value=None):
    executable = shutil.which(value or os.environ.get('SILE_BIN', 'sile'))
    if not executable and not value and not os.environ.get('SILE_BIN'):
        cached = list(Path('/nix/store').glob('*-sile-*/bin/sile'))
        if len(cached) == 1:
            executable = str(cached[0])
    if not executable:
        raise ValueError('SILE executable unavailable; use --sile or SILE_BIN')
    return str(Path(executable).resolve())


def common_inputs(profile, executable, medium):
    paths = [HERE / 'typeset.py', Path(__file__).resolve(), *HERE.glob('classes/*.lua')]
    paths += [HERE.parent / name for name in
              ('oet_books.py', 'oet_publication.py', 'publication_config.py')]
    # Capture the mapping implementation and its data, whichever installation is used.
    if profile.data.get('alignment', {}).get('mapping_books'):
        mapping_engine()
        import BibleOrgSys
        bos = Path(BibleOrgSys.__file__).parent
        paths += list((bos / 'Reference').rglob('*.py'))
        paths += list((bos / 'DataFiles/VersificationMappings').rglob('*.json'))
    for logo in profile.data.get('logos', {}).values():
        if logo.get('enabled', False):
            paths.append(Path(logo[medium]))
    # Profile values include inherited settings. Changing a comment does not rebuild PDFs.
    data = {k: v for k, v in profile.data.items() if k != 'batch'}
    return {'profile': data, 'engine': executable, 'engine_hash': digest(Path(executable)),
            'code_and_assets': {str(p): digest(p) for p in sorted(set(paths))}}


def build_one(target, medium, args, fingerprint, destination, log):
    command = [sys.executable, str(HERE / 'typeset.py'), target.key,
               '--config', str(args.layout_settings.resolve()), '--version', args.version,
               '--paper-size', args.paper_size, '--' + medium, '--sile', args.sile,
               '-o', str(destination)]
    if target.selection.collection:
        command += ['--book-order', target.selection.order]
    with tempfile.TemporaryDirectory(prefix='.pdf-build-', dir=destination.parent) as temporary:
        proof = Path(temporary) / destination.name
        command[command.index('-o') + 1] = str(proof)
        with log.open('w', encoding='utf-8') as stream:
            result = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT)
        if result.returncode:
            raise ValueError(f'{destination.name}: build failed (see {log})\n' + log.read_text()[-1800:])
        record = {'fingerprint': fingerprint, 'filename': destination.name,
                  'bytes': proof.stat().st_size, 'sha256': digest(proof),
                  'pages': pdf_pages(proof), 'draft_version': target.selection.draft_version}
        proof.replace(destination)
    return record


def variants(profile, args):
    """Expand the configured edition/paper matrix; CLI overrides remain explicit."""
    batch = profile.data.get('batch', {})
    versions = [args.version] if args.version else batch.get('versions', [profile.version])
    fallback = batch.get('paper_size', 'B5')  # Older profiles remain supported.
    prints = [args.paper_size] if args.paper_size else batch.get('print_sizes', [fallback])
    screen = args.paper_size or batch.get('screen_size', fallback)
    if not isinstance(versions, list) or not versions or len(set(versions)) != len(versions):
        raise ValueError('batch.versions must be a nonempty list of distinct edition IDs')
    if not isinstance(prints, list) or not prints:
        raise ValueError('batch.print_sizes must be a nonempty list of paper sizes')
    prints = [paper_size(size) for size in prints]
    if len(set(prints)) != len(prints):
        raise ValueError('batch.print_sizes must not repeat a paper size')
    result = []
    for version in versions:
        profile.sides(version)
        result += [(version, 'print', size) for size in prints]
        result.append((version, 'screen', paper_size(screen)))
    return result


def run(args):
    profile = load_profile(args.layout_settings)
    batch = profile.data.get('batch', {})
    matrix = variants(profile, args)
    versions = list(dict.fromkeys(v for v, _, _ in matrix))
    output = args.output_dir or batch.get('output_dir')
    cache = args.cache_dir or batch.get('cache_dir')
    if not output or not cache:
        raise ValueError('set batch.output_dir and batch.cache_dir in TOML, or use CLI overrides')
    output, cache = Path(output).resolve(), Path(cache).resolve()
    prefix = batch.get('url_prefix', '/PDFs/').rstrip('/') + '/'
    url = urlsplit(prefix)
    if (url.scheme and (url.scheme not in ('http', 'https') or not url.netloc)
            or not url.scheme and (not prefix.startswith('/') or prefix.startswith('//'))
            or url.query or url.fragment or '..' in url.path.split('/')):
        raise ValueError('batch.url_prefix must be a site-root path or an absolute HTTP(S) URL')
    targets = {v: catalogue(profile, v) for v in versions}
    only = {code.upper() for code in args.only or []}
    unknown = only - {t.key for ts in targets.values() for t in ts}
    if unknown:
        raise ValueError(f'unknown --only targets: {", ".join(sorted(unknown))}')
    chosen = {v: [t for t in ts if not only or t.key in only] for v, ts in targets.items()}
    if args.list_targets:
        for version, medium, size in matrix:
            for target in chosen[version]:
                print(output / default_pdf_filename(version, target.selection.stem, size, medium))
        return
    args.sile = renderer_executable(args.sile)
    require_poppler()
    jobs = args.jobs if args.jobs is not None else batch.get('jobs', 2)
    if not isinstance(jobs, int) or jobs < 1:
        raise ValueError('jobs must be a positive integer')
    output.mkdir(parents=True, exist_ok=True)
    # Cache and locks are outside public/. Independent destinations have independent locks.
    cache = cache / signature(str(output))[:16]
    cache.mkdir(parents=True, exist_ok=True)
    with (cache / 'build.lock').open('w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ValueError(f'another PDF batch is already writing {output}') from error
        state_file = cache / 'state.json'
        state = json.loads(state_file.read_text()) if state_file.exists() else {}
        common = {m: common_inputs(profile, args.sile, m) for m in ('print', 'screen')}
        pending, skipped, failures = [], 0, []
        for version, medium, size in matrix:
            job_args = argparse.Namespace(**{**vars(args), 'version': version, 'paper_size': size})
            for target in chosen[version]:
                sources = {str(p): digest(p) for p in sorted(set(target.sources))}
                filename = default_pdf_filename(version, target.selection.stem, size, medium)
                fingerprint = signature({'common': common[medium], 'sources': sources,
                    'books': target.selection.codes, 'order': target.selection.order,
                    'draft': target.selection.draft_version, 'version': version,
                    'paper': size, 'medium': medium})
                destination = output / filename
                if not args.force and current(state.get(filename), fingerprint, destination):
                    skipped += 1
                else:
                    pending.append((target, medium, job_args, fingerprint, destination, cache / (filename + '.log')))
        print(f'{len(pending)} PDFs to build; {skipped} unchanged; destination: {output}', flush=True)
        with ThreadPoolExecutor(max_workers=jobs) as pool:
            futures = {}
            for target, medium, job_args, fingerprint, destination, log in pending:
                future = pool.submit(build_one, target, medium, job_args, fingerprint, destination, log)
                futures[future] = destination.name
            for i, future in enumerate(as_completed(futures), 1):
                filename = futures[future]
                try:
                    state[filename] = future.result()
                    atomic_json(state_file, state)
                    print(f'[{i}/{len(pending)}] Built {filename} ({state[filename]["pages"]} pages)', flush=True)
                except (ValueError, OSError, subprocess.CalledProcessError) as error:
                    failures.append(str(error))
                    print(str(error), file=sys.stderr, flush=True)
        if failures:
            raise ValueError(f'{len(failures)} PDF builds failed; previous download manifest retained. Rerun to retry.')
        if only:
            print('Selected targets complete; run without --only to refresh the full download manifest.')
            return
        editions = []
        for version in versions:
            entries = []
            for target in targets[version]:
                entry = {'id': target.key, 'title': target.title, 'group': target.group,
                         'kind': 'collection' if target.selection.collection else 'book',
                         'books': target.selection.codes, 'files': []}
                for v, medium, size in matrix:
                    if v != version:
                        continue
                    name = default_pdf_filename(version, target.selection.stem, size, medium)
                    file = {k: value for k, value in state[name].items() if k != 'fingerprint'}
                    file.update(url=prefix + name, medium=medium,
                                paper_size='Letter' if size.lower() == 'letter' else size.upper())
                    entry['files'].append(file)
                entries.append(entry)
            editions.append({'id': version, 'label': profile.data['editions'][version].get('label', version),
                             'entries': entries})
        first = targets[versions[0]]
        manifest = {'schema_version': 2, 'title': profile.title.replace('\n', ' '),
                    'book_order': first[0].selection.order,
                    'draft_version': first[0].selection.draft_version,
                    'groups': [{'id': t.key, 'title': t.title} for t in first if t.key != 'ALL' and t.selection.collection],
                    'editions': editions}
        atomic_json(output / 'manifest.json', manifest)
        catalogue_file = args.catalogue_file or batch.get('catalogue_file')
        if catalogue_file:
            atomic_json(Path(catalogue_file).resolve(), manifest)
        if batch.get('download_page', {}).get('enabled', False):
            atomic_bytes(output / 'index.htm', download_page(manifest, batch['download_page']).encode())
        total = sum(len(e['files']) for edition in editions for e in edition['entries'])
        print(f'Catalogue ready: {total} PDFs; {output / "manifest.json"}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--script-version", action="version", version=f"v{PREPROCESSOR_VERSION}")
    profile_arguments(parser, HERE)
    parser.add_argument('--output-dir', type=Path, help='override batch.output_dir')
    parser.add_argument('--cache-dir', type=Path, help='override private batch.cache_dir')
    parser.add_argument('--catalogue-file', type=Path, help='also write the download catalogue here (overrides batch.catalogue_file)')
    parser.add_argument('--version', help='build just this edition instead of batch.versions')
    parser.add_argument('--paper-size', help='use this size for both print and screen instead of the configured size matrix')
    parser.add_argument('--jobs', type=int, help='maximum simultaneous SILE jobs')
    parser.add_argument('--sile', help='SILE executable')
    parser.add_argument('--only', nargs='+', help='rebuild selected collections/book codes without changing the catalogue')
    parser.add_argument('--list-targets', action='store_true', help='list output paths without rendering')
    parser.add_argument('--force', action='store_true', help='rebuild even when fingerprints match')
    args = parser.parse_args()
    try:
        run(args)
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(1, f'{error}\n')


if __name__ == '__main__':
    main()
