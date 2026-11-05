#!/usr/bin/env python3
"""Audit a book proof against its ESFM sources (requires pdfplumber).

Usage: python3 PTXPrint/check_pdf.py proof.pdf --build-dir retained-build
"""
import argparse
from collections import defaultdict
import math
from pathlib import Path
import re
import unicodedata

import pdfplumber
from typeset import OET, USFMWriter, paired_book
from oet_books import DC, SETTINGS, read_orders


def normalise(text):
    # Ignore layout whitespace and discretionary hyphens in this text audit.
    text = unicodedata.normalize('NFKD', text).replace('\u034f', '').replace('∙', '·')
    text = re.sub(r"[\s\-‐\u00ad]", "", text)
    # PDF glyph order can reverse Hebrew and reorder its combining marks.
    # Check its letters/marks as a multiset; visual review checks RTL ordering.
    text = re.sub('[\u0590-\u05ff]+', lambda m: ''.join(sorted(unicodedata.normalize('NFD', m[0]))), text)
    return text


def compare(label, expected, actual):
    expected, actual = normalise(expected), normalise(actual)
    if expected != actual:
        index = next((i for i, (a, b) in enumerate(zip(expected, actual)) if a != b),
                     min(len(expected), len(actual)))
        raise AssertionError(f"{label} differs at {index}: "
                             f"{expected[index:index+80]!r} != {actual[index:index+80]!r}")


def audit(pdf_path, build_dir, oet_root=OET, version="OET", start_page=1, code='MRK'):
    aliases = read_orders(SETTINGS)['OET_SOURCE_BOOK_ALIASES'] if SETTINGS.is_file() else {}
    book = paired_book(oet_root, code, version, aliases, chapter_pair=code in DC and version == 'OET')
    writer = USFMWriter()
    writer.book(book)
    expected = {}
    for side in ("rv", "lv"):
        expected[side] = "".join("".join(r.text or "" for r in block.findall("run")) or
                                 ("" if block.find('note') is not None else "◘")
                                 for group in book.iter(side) for block in group if block.tag == 'block')
    expected["heading"] = "".join("".join(r.text or "" for r in h.findall("run"))
                                   for h in book.iter("heading"))
    records = (build_dir / 'proof.parlocs').read_text()
    note_order = [int(n) for n in re.findall(r'\\@noteid\{(\d+)\}\{f\}\{n\}', records)]
    expected["notes"] = "".join(f"{n['number']}{n['edition']}{n['ref']}·{n['kind']}{n['text']}"
                                for number in note_order for n in [writer.notes[number-1]])
    note_lookup = {id(n): i + 1 for i, n in enumerate(book.iter("note"))}
    events = defaultdict(list)
    for side in ("rv", "lv"):
        for group in book.iter(side):
            for block in group:
                if block.get("verse"):
                    chapter = block.get('chapter-label', block.get('ref').split(':')[0])
                    label = (chapter + ':' if block.get('chapter-start') or block.get('verse') == '1' else '') + block.get('verse')
                    events[side].append((label, block.get("ref"), "verse"))
                events[side].extend((str(note_lookup[id(n)]), n.get("ref"), "note")
                                    for n in block.findall("note"))
    actual = defaultdict(str)
    actual_events = defaultdict(list)
    heading_calls = []
    boxes = 0
    body_started = False
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            chars = page.chars
            if any(round(c["size"], 2) == 6.9 for c in chars):
                body_started = True
            if not body_started:
                page.close()
                continue
            left = 43 if (page.page_number + start_page - 1) % 2 else 33
            column = (page.width - 92) / 2 if version == "OET" else page.width - 76
            assert min(c["x0"] for c in chars) >= left - 0.5, page.page_number
            assert max(c["x1"] for c in chars) <= left + page.width - 76 + 0.5, page.page_number
            notechars = [c for c in chars if round(c["size"], 2) == 8.9]
            note_top = min((page.height - c["matrix"][5] for c in notechars), default=page.height)
            if notechars:
                last = max(page.height - c["matrix"][5] for c in notechars)
                target = 77 + math.floor((page.height - 45 - 77) / 12.5) * 12.5
                assert abs(last - target) < 0.03, (page.page_number, last, target)
            small = None
            heading_small = None
            for c in chars:
                size = round(c["size"], 2)
                y = page.height - c["matrix"][5]
                side = ("rv" if c["x0"] < left + column + 8 else "lv") if version == "OET" else version[-2:].lower()
                if y >= note_top - 4 and size != 8.5:
                    actual["notes"] += c["text"]
                elif "Lato" in c["fontname"]:
                    if size == 8.5 and 60 < y < page.height - 40:
                        actual["heading"] += c["text"]
                elif size in (10.4, 9.8, 8.04, 7.35, 7.8, 12.0):
                    # Native qs/bk/sc character styles can retain 12bp;
                    # superscripts use 75% of their edition's body size.
                    actual[side] += c["text"]
                if size in (10.4, 9.8, 8.9, 12.0):
                    phase = (y - 77) / 12.5
                    assert abs(phase - round(phase)) * 12.5 < 0.03, (page.page_number, size, y)
                    assert 76.97 <= y <= page.height - 44.97, ("vertical margin", page.page_number, y)
                if size == 6.9 and y < note_top - 4:
                    if small and small[0] == side and abs(small[2] - y) < 0.01 and abs(small[3] - c["x0"]) < 2:
                        small[1] += c["text"]
                        small[3] = c["x1"]
                    else:
                        small = [side, c["text"], y, c["x1"], page.page_number + start_page - 1]
                        actual_events[side].append(small)
                else:
                    small = None
                if "Lato" in c["fontname"] and 6.35 < c["size"] < 6.4:
                    if heading_small and abs(heading_small[1] - y) < 0.01 and abs(heading_small[2] - c["x0"]) < 0.2:
                        heading_small[0] += c["text"]
                        heading_small[2] = c["x1"]
                    else:
                        heading_small = [c["text"], y, c["x1"], page.page_number + start_page - 1]
                        heading_calls.append(heading_small)
                else:
                    heading_small = None
            # Heading boxes have two horizontal strokes, each approximately 96bp.
            edges = [line for line in page.lines if line["height"] < 0.01 and 94 < line["width"] < 97]
            assert len(edges) % 2 == 0
            boxes += len(edges) // 2
            note_rules = [line for line in page.lines if
                          abs(line["width"] - (page.width - 76)) < 0.1 or abs(line["width"] - 40) < 0.1]
            if note_rules and edges:
                assert max(e["bottom"] for e in edges) + 2 < min(r["top"] for r in note_rules), ("box overlaps notes", page.page_number)
            page.close()
        pages = len(pdf.pages)
    anchors = defaultdict(dict)
    body_note_pages = {}
    for side in ("rv", "lv"):
        # A note call can touch the following verse number. Conversely, a verse
        # bridge contains kerns. Compare the whole sequence, then recover the
        # source's event boundaries without guessing from horizontal spacing.
        rendered = [(char, event[2], event[4]) for event in actual_events[side]
                    for char in normalise(event[1].replace("–", "-"))]
        compare(f"{side} verse labels and calls", "".join(e[0] for e in events[side]),
                "".join(e[0] for e in rendered))
        offset = 0
        for label, ref, kind in events[side]:
            _, y, page = rendered[offset]
            offset += len(normalise(label))
            if kind == "verse":
                anchors[side][ref] = (page, y)
            else:
                body_note_pages[int(label)] = page
    if version == "OET":
        for section in book.findall("section"):
            if not all(section.find(side)[0].get('verse') for side in ['rv', 'lv']):
                continue
            rv = anchors["rv"][section.find("rv")[0].get("ref")]
            lv = anchors["lv"][section.find("lv")[0].get("ref")]
            assert rv[0] == lv[0] and abs(rv[1] - lv[1]) < 0.03, ("section alignment", rv, lv)
    for label in expected:
        compare(label, expected[label], actual[label])
    assert boxes == len(list(book.iter("heading"))), boxes
    assert len(heading_calls) == len(book.findall(".//heading/note"))
    for number, _, _, page in heading_calls:
        body_note_pages[int(number)] = page
    # PTXPrint logs the actual shipped page of every caller and note insertion.
    locations = defaultdict(dict)
    for number, place, page in re.findall(r"\\@noteid\{(\d+)\}\{f\}\{([cn])\}\{(\d+)\}",
                                           records):
        locations[int(number)][place] = int(page)
    assert len(locations) == len(writer.notes), len(locations)
    for number, positions in locations.items():
        assert positions.keys() == {"c", "n"} and positions["c"] == positions["n"], (number, positions)
        if number in body_note_pages:
            assert body_note_pages[number] == positions["n"], (number, positions)
    print(f"{pages} pages: complete text, {boxes} boxes, {len(locations)} same-page notes; "
          "section alignment, margins and body/note grid passed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--build-dir", type=Path, required=True)
    parser.add_argument("--oet-root", type=Path, default=OET)
    parser.add_argument("--version", choices=("OET", "OET-RV", "OET-LV"), default="OET")
    parser.add_argument('--start-page', type=int, default=1, help='printed folio of the first page in a collection part')
    parser.add_argument('--book', default='MRK', help='canonical book code (default: MRK)')
    args = parser.parse_args()
    audit(args.pdf, args.build_dir, args.oet_root, args.version, args.start_page, args.book)
