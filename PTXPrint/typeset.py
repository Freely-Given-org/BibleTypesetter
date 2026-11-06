#!/usr/bin/env python3
"""Typeset ESFM/USFM Bible text using PTXPrint's native XeTeX macros (no GUI required)."""
import argparse
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
from xml.sax.saxutils import escape

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from SILE.typeset import PARAGRAPH, paired_book, paper_size, selected_content
from publication_config import default_profile, profile_arguments, resolve_arguments
from oet_books import selection_arguments, select_books
from oet_publication import (pdf_pages, merge_parts, require_poppler, default_pdf_filename,
                             book_version_labels, toolchain_credit,
                             output_arguments, book_credits, link_publication)

PRESETS = {"b5": ("176mm", "250mm"), "a4": ("210mm", "297mm"),
           "letter": ("8.5in", "11in")}


def dimensions(size):
    return PRESETS[size] if size in PRESETS else tuple(size.split(" x "))


def points(dimension):
    return float(dimension[:-2]) * (72 / 25.4 if dimension.endswith("mm") else 72)


def macros_directory(root=None):
    candidates = [Path(root)] if root else [
        Path("/usr/share/ptx2pdf"), Path("/usr/local/share/ptx2pdf")]
    for candidate in candidates:
        for directory in (candidate / "src", candidate):
            if (directory / "paratext2.tex").is_file() and (directory / "ptx2pdf.sty").is_file():
                return directory.resolve()
    raise ValueError("PTXPrint macros not found; use --ptxprint-root or PTXPRINT_ROOT")


def ptxprint_version(macros):
    """Use metadata belonging to the selected PTXPrint macro installation."""
    if macros is not None:
        project = macros.parent / 'pyproject.toml'
        if project.is_file():
            metadata = tomllib.loads(project.read_text(encoding='utf-8')).get('project', {})
            if metadata.get('name') == 'ptxprint' and metadata.get('version'):
                return 'v' + metadata['version'].removeprefix('v')
        for version_file in (macros.parent / 'version.py', macros.parent / 'python/lib/ptxprint/version.py'):
            if version_file.is_file():
                match = re.search(r'''(?m)^VersionStr\s*=\s*["']([^"']+)''', version_file.read_text())
                if match:
                    return 'v' + match[1].removeprefix('v')
    return '(version unavailable)'


def styled(run, link_number=None, tex=False):
    text = (linked_literal(run.text or '', link_number, tex=tex) if link_number is not None
            else literal(run.text or "", tex=tex))
    styles = run.get("style", "").split()
    # The replacement glyph is absent from Gentium Plus.
    text = text.replace("◘", r"\zmissing ◘\zmissing*")
    for i, style in reversed(list(enumerate(styles))):
        marker = ("+" if i else "") + style
        text = f"\\{marker} {text}\\{marker}*"
    return text


def literal(text, tex=False):
    # PTXPrint interprets a double slash as a layout hint; preserve literal URLs.
    return ''.join(r'\slash ' if c == '/' else
                   f'\\char{ord(c)}\\relax ' if tex and c in '#$%&_{}~^\\' else c for c in text)


def linked_literal(text, number, tex=False):
    """Keep each annotation with its text, outside floating heading/note boxes.

    URL punctuation offers normal breaks; long components also have emergency
    breaks without adding hyphens. Small measured boxes cannot leak a link
    onto an intervening sidebar, as a spanning pdf:bann/pdf:eann can.
    """
    result = []
    for token in re.findall(r'\s+|[^\s/_.?&=#-]+[/_.?&=#-]?|[/_.?&=#-]', text):
        if token.isspace():
            result.append(r'\OETLinkSpace ')
            continue
        for start in range(0, len(token), 12):
            piece = token[start:start+12]
            value = literal(piece, tex=tex).replace(r'\slash ', r'\OETLinkSlash ')
            result.append(f'\\OETLinkPiece {number} {value}\\OETLinkPieceEnd')
            result.append(r'\OETLinkSoftBreak ' if piece[-1] in '/_.?&=#-' else r'\OETLinkLongBreak ')
    return ''.join(result)


class USFMWriter:
    """Emit matched native diglot chunks, with all note kinds in one apparatus."""
    def __init__(self):
        self.notes = []
        self.block_number = 0
        self.links = {}

    def styled(self, run, tex=False):
        href = run.get('href')
        number = self.links.setdefault(href, len(self.links) + 1) if href else None
        return styled(run, number, tex=tex)

    def note(self, node, silent=False):
        number = len(self.notes) + 1
        self.notes.append({"number": number, **node.attrib,
                           "text": "".join(node.itertext())})
        label = f"{node.get('edition')} {node.get('ref')} · {node.get('kind')}"
        payload = "".join(self.styled(run) for run in node)
        caller = "-" if silent else str(number)
        prefix = f"{number} " if silent else ""
        return number, f"\\f {caller} \\ft {prefix}\\+bd {label}\\+bd* {payload}\\f*"

    def content(self, node, tex=False):
        return "".join(self.note(child)[1] if child.tag == "note" else self.styled(child, tex=tex)
                       for child in node)

    def heading(self, heading):
        pieces, notes = [], []
        for child in heading:
            if child.tag == 'note':
                number, note = self.note(child, silent=True)
                pieces.append(f'\\sup {number}\\sup*')
                notes.append(note)
            else:
                pieces.append(self.styled(child))
        return '\\p\n\\s1 ' + ''.join(pieces), notes

    def book(self, book):
        code, version = book.get("code"), book.get("version")
        sides = book.get('sides', 'rv lv').split()
        paired = len(sides) == 2
        intro = [f"\\id {code} {book.get('publication-title', '')}", f"\\h {book.get('name')}"]
        if book.get('opening-title'):
            if book.get('logo-opening-src'):
                intro.append(r'\zlogo \OETOpeningLogo')
            intro.append('\\imt1 ' + literal(book.get('opening-title')).replace('\n', r'\break '))
        for title in book.findall("title"):
            intro.append(f"\\{title.get('kind')} {self.content(title)}")
        if not paired:
            intro.append(f'\\imt2 {version}')
        for paragraph in book.findall("intro"):
            intro.append(f"\\{paragraph.get('kind')} {self.content(paragraph)}")
        credits = book.find('credits')
        if credits is None:
            credits = book_credits(book)
            link_publication(credits, book.get('medium', 'print'))
        intro.append(r'\ib')
        for node in credits:
            if node.get('kind') != 'legend':
                intro.append('\\ip ' + self.content(node))
        intro.append("\\ie")
        body = []
        chapters = dict.fromkeys(sides, 0)
        for index, section in enumerate(book.findall("section")):
            for side in sides:
                if paired:
                    if body:
                        body.append("\\p")
                    body.append("\\lefttext" if side == "rv" else "\\righttext")
                if index == 0:
                    body.extend([f"\\id {code} {book.get(side + '-id', side)}", f"\\h {book.get('name')}"])
                blocks = list(section.find(side))
                heading = section.find("heading") if side == sides[0] else None
                pending_notes = []
                heading_pending = heading is not None
                if heading is not None:
                    # The call stays in the box; its note is inserted at the first
                    # verse because TeX inserts inside a sidebar cannot reach the page.
                    text, pending_notes = self.heading(heading)
                    body.append(text)
                for i, block in enumerate(blocks):
                    if block.tag == 'heading':
                        text, pending_notes = self.heading(block)
                        body.append(text)
                        heading_pending = True
                        continue
                    chapter = int(block.get("ref").split(":")[0])
                    if chapter != chapters[side]:
                        body.append(f"\\c {chapter}")
                        body.append(f"\\OETChapter {block.get('chapter-label', str(chapter))} ")
                        chapters[side] = chapter
                    paragraph = block.get("para")
                    if paragraph or i == 0 or heading_pending:
                        body.append("\\" + ("m" if paragraph == "nb" else paragraph or "m"))
                    heading_pending = False
                    text = self.content(block) or r"\zmissing ◘\zmissing*"
                    text = "".join(pending_notes) + text
                    pending_notes = []
                    # Delayed writes on the first and last lines follow the
                    # actual page breaks, including verses spanning a page turn.
                    self.block_number += 1
                    ref = block.get("ref").split(":", 1)[1]
                    chapter_label = block.get('chapter-label', str(chapter))
                    anchor = f'\\OETRangeMark {self.block_number} {chapter_label}:{ref} '
                    text = anchor + text + anchor
                    if block.get("verse"):
                        if block.get('chapter-start'):
                            body.append(f"\\OETFirstVerseLabel {block.get('verse').split('-')[0]} ")
                        body.append(f"\\v {block.get('verse')} {text}")
                    else:
                        body.append(text)
        for side, label in book_version_labels(book).items():
            body.append('\\p')
            if paired:
                body.append('\\lefttext' if side == 'rv' else '\\righttext')
            # A diglot chunk discards leading vertical glue. An actual empty
            # text line reserves one grid row in both page builders.
            body.append(r'\m \null')
            body.append('\\zbookend ' + literal(label))
        if book.get('toolchain') or book.get('logo-ending-src'):
            # A final synchronised chunk has no right-side text. Its left side
            # reserves the height of one paragraph spanning the full measure.
            if paired:
                body.extend([r'\p', r'\lefttext'])
            body.append(r'\m \null')
            body.append(r'\zbookend \OETFullCredit')
        body.append("\\p")
        if not paired:
            # Flush through the normal one-column page builder. PTXPrint's
            # end-of-book partial-page path can detach notes when a protected
            # heading moves to another page.
            body.append(r"\eject")
        return "\n".join(intro) + "\n", "\n".join(body) + "\n"


def prepare(directory, books, size, version, publication=None, start_page=1):
    layout = publication if publication is not None else (books[0] if books else None)
    screen = layout is not None and layout.get('medium') == 'screen'
    sides = layout.get('sides', 'rv lv').split() if layout is not None else default_profile().sides(version)
    paired = len(sides) == 2
    colours = {key: layout.get('colour-' + key, '000000') for key in ('title', 'heading', 'verse', 'call', 'wj', 'link', 'border')} if layout is not None else {}
    width, height = dimensions(size)
    width_bp, height_bp = points(width), points(height)
    column = (width_bp - 92) / 2 if paired else width_bp - 76
    if column < 140 or height_bp < 300:
        raise ValueError("paper is too small for this layout (columns need 140pt; height needs 300pt)")
    writer = USFMWriter()
    calls = []
    (directory / 'index-pages.tex').write_text('', encoding='utf-8')
    (directory / 'page-ranges.tex').write_text('', encoding='utf-8')
    if publication is not None:
        cover = ['\\id FRT', f'\\h {publication.get("publication-title")}',
                 *([r'\zlogo \OETOpeningLogo'] if publication.get('logo-opening-src') else []),
                 '\\ip \\null\\OETCoverSpace',
                 '\\mt1 ' + publication.get('fulltitle').replace('\n', r'\break '), f"\\mt2 {publication.get('title')}",
                 *([f'\\imt2 {version}'] if not paired else []),
                 f"\\imt2 {publication.get('order')}",
                 '\\imt2 ' + writer.content(publication.find('cover-credit')), '\\ie']
        copyright_page = ['\\id FRT', '\\h ' + publication.get('copyright-heading'), '\\is1 ' + publication.get('copyright-title')]
        for node in publication.find('copyright'):
            copyright_page.append('\\ip ' + writer.content(node))
        copyright_page.append('\\ie')
        contents = ['\\id FRT', '\\h Contents', '\\mt1 Contents']
        for entry in publication.findall('entry'):
            name = entry.get('name') if entry.get('code') == 'FRT' else entry.get('code') + '   ' + entry.get('name')
            contents.append(f"\\ip {name}\\hfill\\OETContentsPage {entry.get('code')} ")
        contents.append('\\ie')
        preface = ['\\id FRT', '\\h Preface']
        for node in (publication.find('preface') if publication.find('preface') is not None else []):
            marker = {'p': 'ip', 'm': 'im', 'li1': 'ili1', 'li2': 'ili2', 'b': 'ib'}.get(node.get('kind'), node.get('kind'))
            preface.append(f'\\{marker} {writer.content(node)}')
        preface.append('\\ie')
        front_parts = [('cover', cover), ('copyright', copyright_page), ('contents', contents)]
        if publication.find('preface') is not None:
            front_parts.append(('preface', preface))
        for filename, lines in front_parts:
            (directory / f'{filename}.usfm').write_text('\n'.join(lines) + '\n', encoding='utf-8')
            calls += [r'\diglotfalse', r'\usediglot{}', f'\\def\\OETBookName{{{filename.title()}}}']
            if filename in {'contents', 'preface'}:
                calls.append(r'\OETOpenRecto')
            code = {'cover': 'TITLE', 'copyright': 'COPYRIGHT', 'contents': 'CONTENTS', 'preface': 'FRT'}[filename]
            calls.append(f'\\OETRecordBook{{{code}}}')
            if filename == 'cover':
                calls.append(r'\OETTitlePagetrue')
            if filename == 'copyright':
                calls.append(r'\stylesheet{copyright.sty}')
            if filename == 'contents':
                calls.append(r'\stylesheet{contents.sty}')
            calls.append(f'\\ptxfile{{{filename}.usfm}}')
            if filename == 'cover':
                calls.append(r'\OETTitlePagefalse')
            if filename in {'contents', 'copyright'}:
                calls.append(r'\stylesheet{oet.sty}')
        (directory / 'contents.sty').write_text('\\Marker ip\n\\FirstLineIndent 0\n\\SpaceAfter 0\n', encoding='utf-8')
        (directory / 'copyright.sty').write_text('\\Marker ip\n\\FontSize 9.3\n\\FirstLineIndent 0\n\\SpaceAfter 12.5\n', encoding='utf-8')
    for book in books:
        code = book.get("code")
        intro, body = writer.book(book)
        (directory / f"{code}-intro.usfm").write_text(intro, encoding="utf-8")
        (directory / f"{code}.usfm").write_text(body, encoding="utf-8")
        calls += [f"\\def\\OETBookName{{{book.get('name')}}}", r"\diglotfalse", r"\usediglot{}"]
        if book.get('recto') == 'true':
            calls.append(r'\OETOpenRecto')
        calls += [f'\\OETRecordBook{{{code}}}', f"\\ptxfile{{{code}-intro.usfm}}"]
        if paired:
            calls += [r"\diglottrue", r"\usediglot{L}"]
        calls.extend([r'\def\OETToolchainText{}', r'\def\OETReadingText{}'])
        if book.get('toolchain'):
            calls.append(r'\def\OETToolchainText{' + book.get('toolchain') + '}')
            reading = book.find('reading-link')
            calls.append(r'\def\OETReadingText{' + (writer.content(reading, tex=True) if reading is not None else '') + '}')
        calls.append(f"\\ptxfile{{{code}.usfm}}")
    (directory / "notes.json").write_text(json.dumps(writer.notes, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    styles = (HERE / "oet.sty").read_text(encoding="utf-8")
    if screen:
        for markers, colour in [
                (['mt1', 'mt2', 'imt1', 'imt2', 'h'], 'title'),
                (['is1', 'is2', 's1'], 'heading'), (['v'], 'verse'),
                (['c', 'fr', 'fv'], 'call'), (['wj'], 'wj'), (['zlink'], 'link')]:
            for marker in markers:
                styles += f'\n\\Marker {marker}\n\\Color x{colours[colour]}\n'
        styles += '\n\\Marker cat:s1box|esb\n\\BorderColor x' + colours['border'] + '\n'
        styles += ('\n\\Marker zcall\n\\StyleType Character\n\\FontSize 9.2\n'
                   '\\Superscript\n\\LeftMargin 0.05\n\\Color x' + colours['call'] +
                   '\n\\Marker f\n\\CallerStyle zcall\n\\NoteCallerStyle zcall\n')
    if sides == ['lv']:
        # Literal book names use extended transliteration letters (e.g. ⱱ)
        # absent from Lato. Gentium also covers these in titles and headers.
        styles += '\n\\Marker h\n\\FontName Gentium Plus\n\\Marker mt1\n\\FontName Gentium Plus\n'
    styles += f"\n\\Marker cat:s1box|esb\n\\Scale {96 / column:.8f}\n"
    for marker in sorted(PARAGRAPH | {"io1", "io2", "im", "ili1", "ili2", "zcontents"}):
        size = 9.8 if sides == ['lv'] else 10.4
        styles += f"\n\\Marker {marker}\n\\FontSize {size}\n\\BaseLine 12.5bp\n"
        if paired:
            styles += f"\n\\Marker {marker}L\n\\FontSize 10.4\n\\BaseLine 12.5bp\n"
            styles += f"\n\\Marker {marker}R\n\\FontSize 9.8\n\\BaseLine 12.5bp\n"
    (directory / "oet.sty").write_text(styles, encoding="utf-8")
    shutil.copyfile(HERE / "oet.tex", directory / "oet.tex")
    setup = [r'\def\regular{"Gentium Plus"}', r'\def\bold{"Gentium Plus/B"}',
             r'\def\italic{"Gentium Plus/I"}', r'\def\bolditalic{"Gentium Plus/BI"}',
             r"\def\pluginlist{}", r"\input paratext2.tex", r"\input ptx-ptxprint.tex",
             r"\diglottrue" if paired else r"\diglotfalse",
             r"\stylesheet{usfm_sb.sty}", r"\stylesheet{ptx2pdf.sty}", r"\stylesheet{oet.sty}",
             f"\\PaperWidth={width}", f"\\PaperHeight={height}",
             f"\\def\\OETVersion{{{version}}}", r"\input oet.tex"]
    if layout is not None:
        for command, key in [('OETLeftLabel', 'rv-label'), ('OETRightLabel', 'lv-label')]:
            setup.append('\\def\\' + command + '{' + literal(layout.get(key, ''), tex=True) + '}')
        for role, command in [('opening', 'OETOpeningGraphic'), ('ending', 'OETEndingGraphic'), ('footer', 'OETFooterGraphic')]:
            source = layout.get(f'logo-{role}-src')
            if source:
                filename = f'logo-{role}.png'
                shutil.copyfile(source, directory / filename)
                w, h = float(layout.get(f'logo-{role}-width')), float(layout.get(f'logo-{role}-height'))
                scale = min(1, (width_bp - 76) / w)
                uri = layout.get(f'logo-{role}-href', '').encode('utf-8').hex()
                setup.append('\\def\\' + command + '{\\OETLogo{' + filename + '}{' + f'{w*scale:.5f}bp' + '}{' + f'{h*scale:.5f}bp' + '}{' + uri + '}}')
    if screen:
        rgb = ' '.join(f'{int(colours["link"][i:i+2], 16) / 255:.6f}' for i in (0, 2, 4))
        setup.append(r'\def\OETLinkColour{' + rgb + '}')
    # Hex PDF strings preserve URI fragments, queries, parentheses and escapes
    # without exposing URL bytes to either TeX or PDF-string interpretation.
    for href, number in writer.links.items():
        setup.append(f'\\expandafter\\def\\csname OETURL{number}\\endcsname{{{href.encode("utf-8").hex()}}}')
    # Align the last note baseline with the body grid, leaving at least 45bp
    # below it. PTXPrint's note box already accounts for the final descender.
    last_baseline = 77 + math.floor((height_bp - 45 - 77) / 12.5) * 12.5
    setup.append(f"\\def\\BottomMarginFactor{{{height_bp - last_baseline:.8f}}}")
    setup.append(f"\\pageno={start_page}")
    if layout is not None and layout.get('page-numbers') == 'centred':
        setup.append(r'\OETCentredFoliostrue')
    (directory / "proof.tex").write_text("\n".join(setup + calls + [r"\bye", ""]), encoding="utf-8")


class NotePlacementError(ValueError):
    """Native diglot retry moved, lost or duplicated a page note."""


def verify_note_pages(records, count):
    locations = {}
    for number, place, page in re.findall(r"\\@noteid\{(\d+)\}\{f\}\{([cn])\}\{(\d+)\}", records):
        positions = locations.setdefault(int(number), {"c": [], "n": []})
        positions[place].append(int(page))
    if locations.keys() != set(range(1, count + 1)):
        raise NotePlacementError("PTXPrint did not report all expected note/caller locations")
    for number, positions in locations.items():
        if len(positions["c"]) != 1 or positions["c"] != positions["n"]:
            raise NotePlacementError(f"Note {number} is not on its calling page: {positions}. "
                             "Use --build-dir to retain the placement records.")


def write_index(directory, pages):
    (directory / 'index-pages.tex').write_text(''.join(
        f'\\expandafter\\def\\csname OETPage{code}\\endcsname{{{page}}}\n'
        for code, page in pages.items()), encoding='utf-8')


def page_verse_ranges(records):
    """Combine the scripture actually printed in either column on each folio."""
    blocks = {}
    for line in records.splitlines():
        number, address, folio = line.split()
        blocks.setdefault((number, address), []).append(int(folio))
    bounds = {}
    for (_, address), folios in blocks.items():
        match = re.fullmatch(r'(\d+):(\d+)([a-z]?)(?:-(\d+)([a-z]?))?', address)
        if not match:
            raise ValueError(f'Invalid reference in PTXPrint running header: {address!r}')
        chapter, first, suffix, last, end_suffix = match.groups()
        lo = (int(chapter), int(first), suffix)
        hi = (int(chapter), int(last), end_suffix) if last else lo
        for page in range(min(folios), max(folios) + 1):
            start, end = bounds.get(page, (lo, hi))
            bounds[page] = min(start, lo), max(end, hi)
    def label(ref):
        return f'{ref[0]}:{ref[1]}{ref[2]}'
    return {page: label(start) if start == end else f'{label(start)} – {label(end)}'
            for page, (start, end) in sorted(bounds.items())}


def update_page_ranges(directory):
    ranges = page_verse_ranges((directory / 'proof.oetrefs').read_text())
    definitions = ''.join(f'\\expandafter\\def\\csname OETRange{page}\\endcsname{{{label}}}\n'
                          for page, label in ranges.items())
    path = directory / 'page-ranges.tex'
    if path.read_text(encoding='utf-8') == definitions:
        return False
    path.write_text(definitions, encoding='utf-8')
    return True


def emergency_word_breaks(directory):
    """Offer last-resort breaks at visible LV joins, preserving every symbol."""
    joins = {'_': ('OETJoinU', 95), '÷': ('OETJoinD', 247), '=': ('OETJoinE', 61)}
    for path in directory.glob('*.usfm'):
        text = path.read_text(encoding='utf-8')
        text = re.sub('[_÷=]', lambda m: '\\' + joins[m[0]][0] + ' ', text)
        path.write_text(text, encoding='utf-8')
    with (directory / 'oet.tex').open('a', encoding='utf-8') as stream:
        for macro, char in joins.values():
            stream.write(f'\n\\def\\{macro}{{\\char{char}\\penalty9999\\relax}}\n')


def note_plan(records, heights, reserves):
    """Assign each captured note once to its actual caller's physical page."""
    callers, groups = {}, {}
    for number, page in re.findall(r'\\@noteid\{(\d+)\}\{f\}\{c\}\{(\d+)\}', records):
        number, page = int(number), int(page)
        if number not in heights:  # Native introduction note.
            continue
        if number in callers:
            raise ValueError(f'Duplicate caller for note {number}')
        callers[number] = page
        groups.setdefault(page, []).append(number)
    if callers.keys() != heights.keys():
        raise ValueError('Captured note has no printed caller')
    for page, numbers in groups.items():
        # Heights are TeX pt; grid dimensions are PDF bp. One extra row
        # separates body text/heading boxes from the note rule.
        height = sum(heights[n] / 1.00375 for n in numbers)
        reserves[page] = max(reserves.get(page, 0), 12.5 * (math.ceil(height / 12.5 - 0.0001) + 1))
    return callers, groups


def run_fixed_notes(directory, xetex, env, count):
    """Converge page reservations without replaying native note insertions.

    Reservations only grow during this fallback, preventing page oscillation.
    Unused space can remain above the apparatus; body and notes keep the grid.
    """
    shutil.copyfile(HERE / 'page_notes.tex', directory / 'page_notes.tex')
    continuing = r'\input page_notes.tex' in (directory / 'oet.tex').read_text()
    if not continuing:
        shutil.copyfile(directory / 'proof.parlocs', directory / 'native-note-failure.parlocs')
        with (directory / 'oet.tex').open('a', encoding='utf-8') as stream:
            # PTXPrint allocates saved figure/sidebar boxes directly from
            # register 1001, outside TeX's normal allocator. Keep a large
            # book's note boxes clear of that range (Psalms exceeds 850 notes).
            # e-TeX's global extended-box allocator uses count264.
            stream.write('\n\\ifnum\\count264<10000 \\global\\count264=10000 \\fi\n')
            for number in range(1, count + 1):
                stream.write(f'\n\\expandafter\\globbox\\csname OETNote{number}\\endcsname')
            stream.write('\n\\input page_notes.tex\n')
        (directory / 'notes-plan.tex').write_text('', encoding='utf-8')
    reserves, previous = {}, None
    if continuing:
        # Retained work can be resumed after interruption without allocating
        # the note boxes twice or discarding the measured page reservations.
        reserves = {int(page): float(height) for page, height in re.findall(
            r'OETReserve(\d+)\\endcsname\{([\d.]+)bp\}',
            (directory / 'notes-plan.tex').read_text())}
    for iteration in range(1, 41):
        result = subprocess.run([xetex, '-no-shell-escape', '-no-pdf', '-interaction=nonstopmode',
                                 '-halt-on-error', 'proof.tex'], cwd=directory, env=env, text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        (directory / 'xetex-output.txt').write_text(result.stdout, encoding='utf-8')
        if result.returncode:
            raise ValueError('XeTeX failed during note pagination:\n' + result.stdout[-4500:])
        heights = {int(n): float(h.removesuffix('pt')) for n, h in
                   (line.split() for line in (directory / 'proof.noteheights').read_text().splitlines())}
        records = (directory / 'proof.parlocs').read_text()
        callers, groups = note_plan(records, heights, reserves)
        state = (callers.copy(), reserves.copy(), records)
        ranges_changed = update_page_ranges(directory)
        if state == previous and not ranges_changed:
            verify_note_pages(records, count)
            (directory / 'note-pagination.json').write_text(json.dumps({
                'passes': iteration, 'caller_pages': callers, 'reserved_bp': reserves,
                'strategy': 'conservative page reserves after native note-placement failure'}, indent=2))
            return
        previous = state
        plan = ''.join(f'\\expandafter\\def\\csname OETReserve{page}\\endcsname{{{height}bp}}\n'
                       for page, height in reserves.items())
        plan += ''.join(f'\\expandafter\\def\\csname OETNotes{page}\\endcsname{{' +
                        ''.join(f'\\OETUseNote{{{n}}}' for n in sorted(numbers)) + '}\n'
                        for page, numbers in groups.items())
        (directory / 'notes-plan.tex').write_text(plan, encoding='utf-8')
    raise ValueError('Page-note reservations did not settle within 40 passes')


def run_engine(directory, macros, xetex, converter, index_pages=None):
    env = os.environ.copy()
    env["TEXINPUTS"] = str(macros) + os.pathsep + env.get("TEXINPUTS", "")
    # A source checkout bundles PTXPrint's required cropmark font. Make it
    # available for this process without installing or changing system fonts.
    fonts = macros.parent / "fonts"
    if fonts.is_dir():
        config = directory / "fonts.conf"
        config.write_text('<fontconfig><include ignore_missing="yes">/etc/fonts/fonts.conf</include>'
                          f'<dir>{escape(str(fonts))}</dir>'
                          '<cachedir prefix="relative">font-cache</cachedir></fontconfig>',
                          encoding="utf-8")
        env["FONTCONFIG_FILE"] = str(config)
    notes = json.loads((directory / 'notes.json').read_text(encoding='utf-8'))
    fixed_notes = r'\input page_notes.tex' in (directory / 'oet.tex').read_text()
    # Note/cutout placement is recorded between passes. Require convergence.
    previous = None
    for iteration in range(1, 6):
        if fixed_notes:
            run_fixed_notes(directory, xetex, env, len(notes))
            break
        if index_pages is not None:
            write_index(directory, index_pages)
        result = subprocess.run([xetex, "-no-shell-escape", "-no-pdf", "-interaction=nonstopmode",
                                 "-halt-on-error", "proof.tex"], cwd=directory, env=env,
                                text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        (directory / "xetex-output.txt").write_text(result.stdout, encoding="utf-8")
        if result.returncode:
            raise ValueError("XeTeX failed:\n" + result.stdout[-4500:])
        pages = dict(line.split() for line in (directory / 'proof.bookpages').read_text().splitlines())
        write_index(directory, {**(index_pages or {}), **pages})
        state = tuple(p.read_bytes() for p in sorted(directory.glob("proof.*"))
                      if p.suffix in {".notepages", ".parlocs", ".picpages", '.bookpages'})
        ranges_changed = update_page_ranges(directory)
        if state == previous and not ranges_changed:
            break
        previous = state
    else:
        raise ValueError("PTXPrint page placement did not settle within five passes")
    try:
        verify_note_pages((directory / 'proof.parlocs').read_text(encoding='utf-8'), len(notes))
    except NotePlacementError:
        print(f'Paginating page notes for {directory.name}', file=sys.stderr, flush=True)
        run_fixed_notes(directory, xetex, env, len(notes))
    log = (directory / "proof.log").read_text(encoding="utf-8", errors="replace")
    # PTXPrint deliberately overfills trial vertical boxes while finding a
    # legal diglot split. Only final output vboxes and actual line overflows
    # are errors here; check_pdf.py audits the resulting page geometry.
    overflow = re.findall(r"Overfull \\hbox \(([\d.]+)pt too wide\)", log)
    if (any(float(amount) > 0.5 for amount in overflow)
            and r'\def\OETJoinU' not in (directory / 'oet.tex').read_text()):
        print(f'Allowing breaks in long source-word joins for {directory.name}', file=sys.stderr, flush=True)
        emergency_word_breaks(directory)
        return run_engine(directory, macros, xetex, converter, index_pages)
    width = re.search(r'\\PaperWidth=([\d.]+(?:mm|in))', (directory / 'proof.tex').read_text())[1]
    full_width = (points(width) - 76) * 1.00375
    # A diglot trial can issue an output-active warning for a tiny column
    # fragment. A shipped page box spans the full text width.
    overflow += [amount for amount, box_width in re.findall(
        r'Overfull \\vbox \(([\d.]+)pt too high\) has occurred while \\output is active\s+\\vbox\([^\n]*\)x([\d.]+)', log)
        if float(box_width) > 0.9 * full_width]
    if "Missing character:" in log or any(float(amount) > 0.5 for amount in overflow):
        raise ValueError("The proof has missing glyphs or overflowing text. "
                         "Use --build-dir to retain proof.log and review the paper size/layout.")
    result = subprocess.run([converter, "-o", "proof.pdf", "proof.xdv"], cwd=directory, env=env,
                            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    (directory / "xdvipdfmx-output.txt").write_text(result.stdout, encoding="utf-8")
    if re.search(r'Interpreting special command .* failed', result.stdout):
        raise ValueError('xdvipdfmx could not create PDF annotations or graphics; see xdvipdfmx-output.txt')
    if result.returncode or not (directory / "proof.pdf").is_file():
        raise ValueError("PDF conversion failed:\n" + result.stdout[-3000:])


def render_publication(directory, books, size, version, publication, macros, xetex, converter):
    """Isolate PTXPrint's per-book cutout/diglot state, preserving folios/parity.

    Each part is still typeset by native PTXPrint. Poppler only concatenates
    the finished pages; it never scales or rasterizes them.
    """
    require_poppler()
    parts, pages = [], {}
    next_page = 1
    front_dir = directory / 'front'
    if publication is not None:
        front_dir.mkdir()
        prepare(front_dir, [], size, version, publication)
        run_engine(front_dir, macros, xetex, converter)
        pages.update(dict(line.split() for line in (front_dir / 'proof.bookpages').read_text().splitlines()))
        next_page += pdf_pages(front_dir / 'proof.pdf')
        parts.append(front_dir / 'proof.pdf')
    front_count = next_page - 1
    for book in books:
        code = book.get('code')
        book_start = next_page + (book.get('recto') == 'true' and next_page % 2 == 0)
        print(f'Typesetting {code} (page {book_start})', file=sys.stderr, flush=True)
        book_dir = directory / code
        book_dir.mkdir()
        prepare(book_dir, [book], size, version, start_page=next_page)
        run_engine(book_dir, macros, xetex, converter)
        pages[code] = str(book_start)
        next_page += pdf_pages(book_dir / 'proof.pdf')
        parts.append(book_dir / 'proof.pdf')
    if publication is not None:
        run_engine(front_dir, macros, xetex, converter, index_pages=pages)
        if pdf_pages(front_dir / 'proof.pdf') != front_count:
            raise ValueError('The contents page count changed after adding page numbers.')
    (directory / 'book-pages.tsv').write_text(''.join(f'{code}\t{page}\n' for code, page in pages.items()))
    merge_parts(parts, directory / 'proof.pdf')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    selection_arguments(parser)
    output_arguments(parser)
    profile_arguments(parser, HERE)
    parser.add_argument("--source-root", "--oet-root", dest="oet_root", type=Path, help="override the configured source root")
    parser.add_argument("-o", "--output", type=Path, help="exact destination (default: VERSION-BOOKS.SIZE.MODE.pdf)")
    parser.add_argument("--paper-size", type=paper_size, default="b5", metavar="SIZE",
                        help='B5 (default), A4, Letter, or dimensions such as "160x240mm" or "6x9in"')
    parser.add_argument("--version", help="edition ID from TOML (default: publication.default_version)")
    parser.add_argument("--ptxprint-root", type=Path, default=os.environ.get("PTXPRINT_ROOT"),
                        help="PTXPrint checkout or installed macro directory")
    parser.add_argument("--xetex", default=os.environ.get("XETEX_BIN", "xetex"))
    parser.add_argument("--xdvipdfmx", default=os.environ.get("XDVIPDFMX_BIN", "xdvipdfmx"))
    parser.add_argument("--build-dir", type=Path, help="keep generated USFM, TeX, styles and logs here")
    parser.add_argument("--prepare-only", action="store_true", help="write inputs without rendering (requires --build-dir)")
    args = parser.parse_args()
    try:
        profile = resolve_arguments(args)
        selection = select_books(args)
    except (ValueError, OSError) as error:
        parser.error(str(error))
    if args.list_books:
        print(' '.join(selection.codes)); return
    if args.prepare_only and not args.build_dir:
        parser.error("--prepare-only requires --build-dir")
    output = (args.output or Path(default_pdf_filename(args.version, selection.stem, args.paper_size, args.medium))).resolve()
    if output.suffix.lower() != ".pdf":
        parser.error("output filename must end in .pdf")
    try:
        try:
            macros = macros_directory(args.ptxprint_root or profile.data.get('tools', {}).get('ptxprint_root'))
        except ValueError:
            if not args.prepare_only:
                raise
            macros = None
        credit = toolchain_credit('PTXPrint ' + ptxprint_version(macros))
        books, publication = selected_content(args, selection, credit)
        if not args.prepare_only:
            xetex, converter = shutil.which(args.xetex), shutil.which(args.xdvipdfmx)
            if not xetex or not converter:
                raise ValueError("XeTeX and xdvipdfmx are required. Install texlive-xetex, or use --xetex/--xdvipdfmx.")
        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".oet-ptx-", dir=output.parent) as temporary:
            directory = Path(temporary)
            try:
                prepare(directory, books, args.paper_size, args.version, publication)
                if not args.prepare_only:
                    if len(books) > 1 or publication is not None:
                        render_publication(directory, books, args.paper_size, args.version, publication,
                                           macros, xetex, converter)
                    else:
                        run_engine(directory, macros, xetex, converter)
                    (directory / "proof.pdf").replace(output)
            finally:
                if args.build_dir:
                    shutil.copytree(directory, args.build_dir.resolve(), dirs_exist_ok=True)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"{error}\n")
    print(args.build_dir.resolve() if args.prepare_only else output)


if __name__ == "__main__":
    main()
