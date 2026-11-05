#!/usr/bin/env python3
"""Print OET ESFM books with SILE. Run with --help for usage."""
import argparse
from bisect import bisect_right
from dataclasses import dataclass, field
from pathlib import Path
import os
import math
import re
import shutil
import subprocess
import tempfile
import sys
import json
from functools import lru_cache
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from oet_books import selection_arguments, select_books, source_path, OT
from oet_publication import (pdf_pages, merge_parts, require_poppler, default_pdf_filename,
                             TITLE, draft_credit, copyright_paragraphs, book_version_labels)
OET = HERE.parent.parent / "OpenEnglishTranslation--OET"
MARKER = re.compile(r"\\\+?(\w+)(\*| ?)")
NOTES = re.compile(r"\\(f|x) (.*?)\\\1\*")
INLINE = {"add", "wj", "nd", "em", "it", "bd", "bdit", "bk", "sig", "sup", "untr", "ior", "sc", "qs", "wh"}
ADD_CODES = re.compile(r"(\\\+?add )[-?+¿=<>≡&*@#%^≈!]+")
PARAGRAPH = {"p", "m", "nb", "pi", "pi1", "pi2", "q1", "q2", "q3", "li1", "li2", "mi", "b", "pc", "qa", "sp", "d"}
INTRO = {"is1", "is2", "ip", "iot", "io1", "io2", "im", "ili1"}


def paper_size(value):
    """Accept named stock or width x height, with shared or individual units."""
    value = value.strip().lower()
    if value in {"a4", "b5", "letter"}:
        return value
    dimension = r"(\d+(?:\.\d*)?|\.\d+)\s*(mm|inches|inch|in)?"
    match = re.fullmatch(fr"{dimension}\s*[x×]\s*{dimension}", value)
    if not match:
        raise argparse.ArgumentTypeError('use A4, B5, Letter, "210x297mm", or "8.5x11in"')
    width, width_unit, height, height_unit = match.groups()
    width_unit = width_unit or height_unit
    height_unit = height_unit or width_unit
    if not width_unit:
        raise argparse.ArgumentTypeError("custom paper dimensions need mm or inch units")
    dimensions = []
    for number, unit in ((width, width_unit), (height, height_unit)):
        if not math.isfinite(float(number)) or float(number) <= 0:
            raise argparse.ArgumentTypeError("paper dimensions must be finite and positive")
        dimensions.append(number + ("mm" if unit == "mm" else "in"))
    return " x ".join(dimensions)


def clean(text):
    text = re.sub(r"¦[0-9]+", "", text)
    text = re.sub(r"\\fig .*?\\fig\*", "", text)
    text = re.sub(r'\\jmp ([^|]+)\|[^\\]*\\jmp\*', r"\1", text)
    # OET's experimental discourse/highlight controls are not printed text.
    text = re.sub(r"\\z(?:[1-4](?:hilite)?|r)(?:\*| ?)", "", text)
    return ADD_CODES.sub(r"\1", text).replace("⇔", "").removeprefix("≈").replace("'", "’")


def inline(parent, text):
    """Retain adjacent styled fragments, including joins inside LV words."""
    stack = []
    pos = 0
    for marker in MARKER.finditer(text):
        if marker.start() > pos:
            ET.SubElement(parent, "run", style=" ".join(stack)).text = text[pos:marker.start()]
        tag, ending = marker.groups()
        if tag not in INLINE:
            raise ValueError(f"unsupported character marker {tag} in {text[:100]}")
        if ending == "*":
            if not stack or stack.pop() != tag:
                raise ValueError(f"unmatched closing marker {tag} in {text[:100]}")
        else:
            stack.append(tag)
        pos = marker.end()
    if pos < len(text):
        ET.SubElement(parent, "run", style=" ".join(stack)).text = text[pos:]
    if stack:
        raise ValueError(f"unclosed character marker {stack[-1]} in {text[:100]}")
    # A few translator notes contain Hebrew without an explicit \wh span.
    # Keep it intact and choose a font with Hebrew glyphs in both backends.
    for run in list(parent):
        if run.tag == 'run' and 'wh' not in run.get('style', '').split() and re.search('[\u0590-\u05ff]', run.text or ''):
            offset = list(parent).index(run)
            parent.remove(run)
            for piece in re.split('([\u0590-\u05ff]+)', run.text):
                if piece:
                    node = ET.Element('run', style=run.get('style', '') + (' wh' if re.search('[\u0590-\u05ff]', piece) else ''))
                    node.text = piece; parent.insert(offset, node); offset += 1
    for run in list(parent):
        if run.tag == 'run' and re.search('[◘😀]', run.text or ''):
            offset = list(parent).index(run)
            parent.remove(run)
            for piece in re.split('([◘😀])', run.text):
                if piece:
                    node = ET.Element('run', style=run.get('style', '') + (' zsymbol' if piece in {'◘', '😀'} else ''))
                    node.text = piece
                    parent.insert(offset, node)
                    offset += 1


def content(parent, text, ref, edition):
    text = clean(text)
    # Keep open spans across note calls. Internal placeholders are parsed as
    # inline runs first so the surrounding word and its formatting stay intact.
    notes = []

    def take_note(match):
        kind, payload = match.groups()
        payload = re.sub(r"^\S+\s+", "", payload, count=1)
        origin = re.match(r"\\(?:fr|xo)\s+(.*?)\s*(?=\\)", payload)
        address = origin[1].strip().rstrip(":") if origin else ref
        payload = payload[origin.end():] if origin else payload
        payload = re.sub(r"\\(?:ft|xt|fq|fqa|fk|fl) ", "", payload)
        note = ET.Element("note", kind="Note" if kind == "f" else "Cross-ref.",
                          ref=address, edition=edition)
        inline(note, payload)
        notes.append(note)
        return "\x00"

    inline(parent, NOTES.sub(take_note, text))
    if notes:
        runs = list(parent)
        parent[:] = []
        pending = iter(notes)
        for run in runs:
            for i, piece in enumerate(run.text.split("\x00")):
                if i:
                    parent.append(next(pending))
                if piece:
                    ET.SubElement(parent, "run", run.attrib).text = piece


@dataclass
class Edition:
    name: str = ""
    credit: str = ""
    source_version: str = ""
    set_release: str = ""
    title: list = field(default_factory=list)
    intro: list = field(default_factory=list)
    blocks: list = field(default_factory=list)
    headings: dict = field(default_factory=dict)
    addresses: set = field(default_factory=set)


def lv_set_release(source):
    """Read the release of the LV set that supplied this ESFM file."""
    path = source.with_name('version.json')
    try:
        manifest = json.loads(path.read_text(encoding='utf-8-sig'))
    except FileNotFoundError:
        return ''  # Older checkouts only have the ESFM ID.
    except ValueError as error:
        raise ValueError(f'{path}: {error}') from error
    if not isinstance(manifest, dict) or manifest.get('resource', 'OET-LV') != 'OET-LV':
        raise ValueError(f'{path}: expected an OET-LV release')
    version = manifest.get('version')
    group = manifest.get('group', '')
    if not isinstance(version, str) or not version.strip() or not isinstance(group, str):
        raise ValueError(f'{path}: invalid release version or group')
    return f'{version.strip()} ({group.strip()} set)' if group.strip() else version.strip()


def read_edition(path, edition):
    book = Edition()
    if edition == 'LV':
        book.set_release = lv_set_release(path)
    chapter = 0
    ref = None
    key = None
    paragraph = "m"
    heading = None
    pending = []
    chapter_label = None
    verse_chapters = set()
    for number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        if not line.strip():
            continue
        tag, _, text = line.strip().partition(" ")
        tag = tag.removeprefix("\\")
        try:
            if tag == 'id':
                match = re.search(r'\b[vV]\d+(?:\.\d+)+(?:[-+][\w.-]+)?', text)
                book.source_version = match[0] if match else ''
                continue
            if tag == "rem" and not chapter and "source table" in text and "Copyright" in text:
                book.credit = text
            if tag in {"id", "usfm", "ide", "rem", "toc1", "toc2", "toc3", "ie"}:
                continue
            if tag == "h":
                name = ET.Element('name')
                inline(name, clean(text))
                book.name = ''.join(name.itertext())
                continue
            if not chapter and tag.startswith("mt"):
                book.title.append((tag, clean(text)))
                continue
            if not chapter and tag in INTRO:
                node = ET.Element("intro", kind=tag)
                content(node, text, "", edition)
                book.intro.append(node)
                continue
            if tag == "c":
                chapter = int(text)
                paragraph = "m"
                chapter_label = None
                continue
            if tag in {"cl", "cp"}:
                if tag == "cp":
                    chapter_label = text
                else:
                    book.intro.append(ET.fromstring("<intro kind='im'><run/></intro>"))
                    book.intro[-1][0].text = "Chapter label: " + text
                continue
            if tag in {"s1", "s2", "s3", "s4", "ms1"}:
                if heading is None:
                    heading = ET.Element("heading")
                else:
                    ET.SubElement(heading, "run").text = " · "
                content(heading, text, "", edition)
                continue
            if tag in {"r", "mr", "sr"} and heading is not None:
                note = ET.SubElement(heading, "note", kind="Parallel", edition=edition)
                ET.SubElement(note, "run").text = clean(text).removeprefix("(").removesuffix(")")
                continue
            if tag in PARAGRAPH:
                paragraph = tag
                if not text:
                    continue
                address = ref if key and key[0] == chapter else f"{chapter}:1"
                node = ET.Element("block", ref=address, para=paragraph)
                content(node, text, address, edition)
                if key is None or key[0] != chapter or heading is not None:
                    pending.append(node)
                else:
                    book.blocks.append((key, node))
                paragraph = ""
                continue
            elif tag == "v":
                label, _, text = text.partition(" ")
                if not re.fullmatch(r"\d+[a-z]?(?:-\d+[a-z]?)?", label):
                    raise ValueError(f"unsupported verse label {label}")
                first, suffix = re.fullmatch(r"(\d+)([a-z]?)", label.split("-")[0]).groups()
                first, last = int(first), int(re.match(r"\d+", label.split("-")[-1])[0])
                key = chapter, first, suffix
                if not chapter or first > last or key in book.addresses:
                    raise ValueError(f"invalid or duplicate verse {chapter}:{label}")
                book.addresses.update((chapter, n, suffix) for n in range(first, last + 1))
                ref = f"{chapter}:{label}"
                if heading is not None:
                    for note in heading.findall("note"):
                        if not note.get("ref"):
                            note.set("ref", ref)
                    book.headings[key] = heading
                    heading = None
                for before in pending:
                    book.blocks.append((key, before))
                pending.clear()
                node = ET.Element("block", ref=ref, para=paragraph, verse=label)
                if chapter not in verse_chapters:
                    node.set('chapter-start', 'true')
                    verse_chapters.add(chapter)
                if chapter_label:
                    node.set("chapter-label", chapter_label)
            else:
                raise ValueError(f"unsupported line marker {tag}")
            content(node, text, ref, edition)
            book.blocks.append((key, node))
            paragraph = ""
        except ValueError as error:
            raise ValueError(f"{path}:{number}: {error}") from error
    if not book.blocks or heading is not None or pending:
        raise ValueError(f"{path}: missing verses or a final heading without an anchor")
    return book


@lru_cache(maxsize=1)
def mapping_engine():
    try:
        from BibleOrgSys.Reference.BibleVersificationMappings import get_default_mapping_engine
    except ImportError:
        sys.path.insert(0, str(HERE.parent.parent / 'BibleOrgSys'))
        try:
            from BibleOrgSys.Reference.BibleVersificationMappings import get_default_mapping_engine
        except ImportError as error:
            raise ValueError('OT pairing needs BibleOrgSys verse mappings (install it or keep its checkout alongside this repository)') from error
    return get_default_mapping_engine()


def mapped_lv_keys(code, rv, lv):
    engine = mapping_engine()
    result = []
    represented = set()
    previous = None
    for key, block in lv.blocks:
        if block.get('verse'):
            refs = [(code, key[0], v, key[2] or None)
                    for v in range(key[1], int(re.match(r'\d+', block.get('verse').split('-')[-1])[0]) + 1)]
            mapping = engine.convert_passage('OET-LV', 'OET-RV', refs)
            if mapping.status != 'exact':
                raise ValueError(f'{code} {block.get("ref")}: cannot map LV to RV: {mapping.status.value}')
            targets = {(int(r.C), int(r.V), r.S or '') for r in mapping.references}
            missing = {r for r in targets if r[1] != 0} - rv.addresses
            if missing:
                raise ValueError(f'{code}: mapped RV verses missing: {sorted(missing)}')
            represented.update(targets)
            # A Psalm's unnumbered RV title belongs with that Psalm's first verse.
            previous = min((c, max(1, v), s) for c, v, s in targets)
            block.set('align-end', ':'.join(map(str, max((c, max(1, v), s) for c, v, s in targets))))
        result.append((previous or key, block))
    for address in sorted(rv.addresses - represented):
        absence = engine.convert_passage('OET-RV', 'OET-LV', [(code, *address[:2], address[2] or None)])
        if not any(d.code == 'NO_REFERENCE_COUNTERPART' for d in absence.diagnostics):
            raise ValueError(f'{code}: RV verse has no mapped LV text: {address}')
        node = ET.Element('block', ref=f'{address[0]}:{address[1]}', para='m')
        ET.SubElement(node, 'run', style='it').text = f'No LV counterpart for RV {address[0]}:{address[1]}.'
        result.insert(next((i for i, (key, _) in enumerate(result) if key > address), len(result)), (address, node))
    return result


def paired_book(root, code, version="OET", aliases=None, chapter_pair=False):
    """Prepare the selected edition(s), pairing by RV sections in OET mode."""
    editions = {}
    if version in {"OET", "OET-RV"}:
        path = source_path(root, 'RV', code, aliases, required=not chapter_pair)
        if path:
            editions["rv"] = read_edition(path, "RV")
    if version in {"OET", "OET-LV"}:
        path = source_path(root, 'LV', code, aliases, required=not chapter_pair)
        if path:
            editions["lv"] = read_edition(path, "LV")
    if not editions:
        raise ValueError(f'{code}: no source text available')
    if version == "OET" and not chapter_pair:
        rv, lv = editions["rv"], editions["lv"]
        if code in OT or code == 'ACT':
            lv.blocks = mapped_lv_keys(code, rv, lv)
        elif rv.addresses != lv.addresses:
            raise ValueError(f"{code}: verse coverage differs at {sorted(rv.addresses ^ lv.addresses)[:8]}")
        if lv.headings:
            raise ValueError(f"{code}: headings in the Literal Version require review")
    primary = next(iter(editions.values()))
    credit = " ".join(edition.credit for edition in editions.values() if edition.credit)
    book = ET.Element("book", code=code, name=primary.name, credit=credit, version=version)
    for side, edition in editions.items():
        book.set(side + '-source-version', edition.source_version)
        if edition.set_release:
            book.set(side + '-set-release', edition.set_release)
    for side, label in book_version_labels(book).items():
        book.set(side + '-colophon', label)
    for kind, text in primary.title:
        node = ET.SubElement(book, "title", kind=kind)
        inline(node, text)
    book.extend(primary.intro)
    if chapter_pair:
        notice = ET.SubElement(book, 'intro', kind='ip')
        ET.SubElement(notice, 'run').text = ('The DC editions are placed side by side by chapter only. '
            'Their verse numbering and textual contents differ; corresponding lines are not established equivalents.')
        chapters = sorted({key[0] for edition in editions.values() for key, _ in edition.blocks})
        for chapter in chapters:
            section = ET.SubElement(book, 'section')
            for side in ('rv', 'lv'):
                target = ET.SubElement(section, side)
                edition = editions.get(side)
                if edition:
                    emitted = set()
                    for key, block in edition.blocks:
                        if key[0] != chapter:
                            continue
                        if key in edition.headings and key not in emitted:
                            target.append(edition.headings[key]); emitted.add(key)
                        target.append(block)
                if not len(target):
                    block = ET.SubElement(target, 'block', ref=f'{chapter}:1', para='m')
                    ET.SubElement(block, 'run', style='it').text = f'No {side.upper()} source text for chapter {chapter}.'
        return book
    starts = sorted({primary.blocks[0][0], *primary.headings})
    sections = []
    for key in starts:
        section = ET.SubElement(book, "section")
        if key in primary.headings:
            section.append(primary.headings[key])
        sections.append({name: ET.SubElement(section, name) for name in editions})
    for name, edition in editions.items():
        for key, block in edition.blocks:
            idx = bisect_right(starts, key) - 1
            if idx + 1 < len(starts) and "verse" in block.attrib:
                end = key[0], int(re.match(r"\d+", block.get("verse").split("-")[-1])[0]), ""
                if block.get('align-end'):
                    c, v, s = block.get('align-end').split(':')
                    end = int(c), int(v), s
                if end >= starts[idx + 1]:
                    raise ValueError(f"{code}: {name} verse bridge crosses a section at {starts[idx+1]}")
            sections[idx][name].append(block)
    return book


def publication_front(root, selection, version, books):
    publication = ET.Element('publication', title=selection.title, version=version,
                             fulltitle=TITLE,
                             order={'oet': 'OET book order', 'traditional': 'Traditional book order', 'given': 'Selected book order'}[selection.order])
    copyright_page = ET.SubElement(publication, 'copyright')
    for text in copyright_paragraphs(selection.draft_version):
        ET.SubElement(ET.SubElement(copyright_page, 'intro', kind='ip'), 'run').text = text
    ET.SubElement(publication, 'entry', code='FRT', name='OET Readers’ Version preface', page='0')
    for book in books:
        ET.SubElement(publication, 'entry', code=book.get('code'), name=book.get('name'), page='0')
    preface = ET.SubElement(publication, 'preface')
    active = False
    path = root / 'translatedTexts/ReadersVersion/OET-RV_FRT.ESFM'
    for number, line in enumerate(path.read_text(encoding='utf-8-sig').splitlines(), 1):
        if not line.strip():
            continue
        tag, _, text = line.strip().partition(' ')
        tag = tag.removeprefix('\\')
        if tag == 'periph':
            if active:
                break
            active = text.strip().lower() == 'preface'
        elif active:
            if tag not in PARAGRAPH | INTRO | {'mt1', 'mt2', 'mt3'}:
                raise ValueError(f'{path}:{number}: unsupported preface marker {tag}')
            node = ET.SubElement(preface, 'intro', kind=tag)
            content(node, text, '', 'RV')
    if not len(preface):
        raise ValueError(f'{path}: Preface peripheral not found')
    return publication


def selected_content(args, selection):
    books = [paired_book(args.oet_root, code, args.version, selection.aliases,
                         chapter_pair=args.version == 'OET' and code in selection.dc)
             for code in selection.codes]
    for book in books:
        book.set('draft-credit', draft_credit(selection.draft_version))
        book.set('recto', str(getattr(args, 'start_books_on_odd_pages', False)).lower())
    front = publication_front(args.oet_root, selection, args.version, books) if selection.front else None
    return books, front


def render_sile(directory, root, executable):
    source, proof = directory / 'parallel.xml', directory / 'proof.pdf'
    ET.ElementTree(root).write(source, encoding='utf-8', xml_declaration=True)
    config = directory / 'fonts.conf'
    config.write_text('<fontconfig><include>/etc/fonts/fonts.conf</include>'
                      '<cachedir prefix="relative">font-cache</cachedir></fontconfig>')
    result = subprocess.run([executable, '-o', str(proof), str(source)], cwd=HERE,
                            env={**os.environ, 'FONTCONFIG_FILE': str(config)}, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    (directory / 'sile-output.txt').write_text(result.stdout, encoding='utf-8')
    if result.returncode:
        raise ValueError('SILE failed:\n' + result.stdout[-4000:])
    return proof


def render_publication(directory, books, front, size, executable):
    """Bound SILE's glyph-cache memory by rendering one book per process."""
    require_poppler()
    parts, pages = [], {}
    next_page = 1
    if front is not None:
        front_dir = directory / 'front'
        front_dir.mkdir()
        front.set('pagefile', str(front_dir / 'book-pages.tsv'))
        front_root = ET.Element('sile', {'class': 'oet', 'papersize': size})
        front_root.append(front)
        parts.append(render_sile(front_dir, front_root, executable))
        next_page += pdf_pages(parts[-1])
        pages.update(dict(line.split('\t') for line in (front_dir / 'book-pages.tsv').read_text().splitlines()))
    front_count = next_page - 1
    for book in books:
        code = book.get('code')
        book_start = next_page + (book.get('recto') == 'true' and next_page % 2 == 0)
        print(f'Typesetting {code} (page {book_start})', file=sys.stderr, flush=True)
        book_dir = directory / code
        book_dir.mkdir()
        book.set('startpage', str(next_page))
        book_root = ET.Element('sile', {'class': 'oet', 'papersize': size})
        book_root.append(book)
        parts.append(render_sile(book_dir, book_root, executable))
        pages[code] = str(book_start)
        next_page += pdf_pages(parts[-1])
    if front is not None:
        for entry in front.findall('entry'):
            entry.set('page', pages[entry.get('code')])
        render_sile(front_dir, front_root, executable)
        if pdf_pages(parts[0]) != front_count:
            raise ValueError('The contents page count changed after adding page numbers.')
    (directory / 'book-pages.tsv').write_text(''.join(f'{code}\t{page}\n' for code, page in pages.items()))
    merge_parts(parts, directory / 'proof.pdf')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    selection_arguments(parser)
    parser.add_argument("--oet-root", type=Path, default=OET, help="OpenEnglishTranslation--OET checkout")
    parser.add_argument("-o", "--output", type=Path, help="exact destination (default: VERSION-BOOKS.SIZE.pdf)")
    parser.add_argument("--paper-size", type=paper_size, default="b5", metavar="SIZE",
                        help='B5 (default), A4, Letter, or width x height, e.g. "210x297mm" or "8.5x11in"')
    parser.add_argument("--version", type=str.upper, choices=("OET", "OET-RV", "OET-LV"), default="OET",
                        help="paired OET (default), or a single version in one full-width column")
    parser.add_argument("--sile", default=os.environ.get("SILE_BIN"), help="SILE 0.15 executable")
    parser.add_argument('--build-dir', type=Path, help='retain generated XML and book-page records')
    parser.add_argument('--prepare-only', action='store_true', help='write XML without rendering (requires --build-dir)')
    args = parser.parse_args()
    try:
        selection = select_books(args)
    except (ValueError, OSError) as error:
        parser.error(str(error))
    if args.list_books:
        print(' '.join(selection.codes)); return
    if args.prepare_only and not args.build_dir:
        parser.error('--prepare-only requires --build-dir')
    output = (args.output or Path(default_pdf_filename(args.version, selection.stem, args.paper_size))).resolve()
    if output.suffix.lower() != ".pdf":
        parser.error("output filename must end in .pdf")
    executable = shutil.which(args.sile or "sile")
    if not executable and not args.sile:
        # A cached Nix flake may be installed without a profile or PATH entry.
        cached = list(Path("/nix/store").glob("*-sile-*/bin/sile"))
        if len(cached) == 1:
            executable = str(cached[0])
    if not executable and not args.prepare_only:
        parser.exit(1, "SILE executable unavailable. Set --sile or SILE_BIN.\n")
    executable = str(Path(executable).absolute()) if executable else None
    root = ET.Element("sile", {"class": "oet", "papersize": args.paper_size})
    try:
        books, front = selected_content(args, selection)
        if front is not None:
            root.append(front)
        root.extend(books)
        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".oet-", dir=output.parent) as tmp:
            directory = Path(tmp)
            try:
                ET.ElementTree(root).write(directory / 'parallel.xml', encoding='utf-8', xml_declaration=True)
                if not args.prepare_only:
                    if len(books) > 1 or front is not None:
                        render_publication(directory, books, front, args.paper_size, executable)
                    else:
                        render_sile(directory, root, executable)
                    (directory / 'proof.pdf').replace(output)
            finally:
                if args.build_dir:
                    shutil.copytree(tmp, args.build_dir.resolve(), dirs_exist_ok=True)
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"{error}\n")
    print(args.build_dir.resolve() if args.prepare_only else output)


if __name__ == "__main__":
    main()
