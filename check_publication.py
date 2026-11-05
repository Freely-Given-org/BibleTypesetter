#!/usr/bin/env python3
"""Check publication metadata, recto starts, index targets and FRT preface (pdfplumber)."""
import argparse
from pathlib import Path
import re

import pdfplumber

from oet_books import selection_arguments, select_books
from SILE.typeset import OET, selected_content
from oet_publication import TITLE, book_version_labels


def normalise(text):
    return re.sub(r'[\s\-‐\u00ad]', '', text).replace('∙', '·')


def body_text(page):
    return ''.join(c['text'] for c in page.chars
                   if 55 < page.height - c['matrix'][5] < page.height - 40)


def audit(pdf_path, build_dir, selection, books, front, recto=False):
    pages = dict(
        (c, int(p)) for c, p in (line.split('\t') for line in (build_dir / 'book-pages.tsv').read_text().splitlines()))
    assert list(pages) == ['TITLE', 'COPYRIGHT', 'CONTENTS', 'FRT', *selection.codes], 'Book order or index membership differs'
    assert list(pages.values()) == sorted(set(pages.values())), 'Book starts are not increasing'
    assert pages['TITLE'] == 1 and pages['COPYRIGHT'] == 2, 'Copyright must be on the title verso'
    assert pages['CONTENTS'] % 2 == pages['FRT'] % 2 == 1, 'Contents and preface must start recto'
    if recto:
        assert all(pages[c] % 2 == 1 for c in selection.codes), 'A book starts on a verso'
    with pdfplumber.open(pdf_path) as pdf:
        assert pages[selection.codes[-1]] <= len(pdf.pages)
        trim = (pdf.pages[0].width, pdf.pages[0].height)
        assert all((p.width, p.height) == trim for p in pdf.pages), 'Page sizes differ, including blank versos'
        cover = normalise(pdf.pages[0].extract_text() or '')
        assert normalise(TITLE) in cover, 'Wrong title'
        assert 'Translationdraft' not in cover, 'Draft version belongs on the verso'
        copyright_page = normalise(pdf.pages[1].extract_text() or '')
        for paragraph in front.find('copyright'):
            assert normalise(''.join(paragraph.itertext())) in copyright_page, 'Copyright text missing from title verso'
        index = ''.join(p.extract_text() or '' for p in pdf.pages[pages['CONTENTS']-1:pages['FRT']-1])
        for entry in front.findall('entry'):
            code = entry.get('code')
            text = ('' if code == 'FRT' else code) + entry.get('name') + str(pages[code])
            assert normalise(text) in normalise(index), f'Index entry missing/wrong: {code}'
        preface = ''.join(body_text(p) for p in pdf.pages[pages['FRT']-1:pages[selection.codes[0]]-1])
        expected = normalise(''.join(front.find('preface').itertext()))
        actual = normalise(preface)
        if expected != actual:
            at = next((i for i, (a, b) in enumerate(zip(expected, actual)) if a != b), min(len(expected), len(actual)))
            raise AssertionError(f'Preface differs at {at}: {expected[at:at+70]!r} != {actual[at:at+70]!r}')
        for position, book in enumerate(books):
            code = book.get('code')
            page = pdf.pages[pages[code]-1]
            title = normalise(''.join(book.find('title').itertext()))
            assert title in normalise(body_text(page)), f'Wrong index destination: {code}'
            end = pages[selection.codes[position+1]]-1 if position+1 < len(selection.codes) else len(pdf.pages)
            # A recto start can leave a blank verso at the end of the prior part.
            final_page = pdf.pages[end-1]
            while not final_page.chars and end > pages[code]:
                end -= 1
                final_page = pdf.pages[end-1]
            ending = normalise(final_page.extract_text() or '')
            for label in book_version_labels(book).values():
                assert normalise(label) in ending, f'Book revision missing at end of {code}: {label}'
            if code in selection.dc and book.get('version') == 'OET':
                # Long introductions can place the notice on a later intro page.
                text = ''
                for intro_page in pdf.pages[pages[code]-1:end]:
                    text += normalise(body_text(intro_page))
                    intro_page.close()
                    if normalise('chapter only') in text:
                        break
                assert normalise('chapter only') in text, f'DC notice absent: {code}'
            page.close()
            final_page.close()
        print(f'{len(pdf.pages)} pages; {len(books)} ordered books; title, copyright, recto starts, book revisions, index targets and complete FRT preface passed.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    selection_arguments(parser)
    parser.add_argument('--pdf', type=Path, required=True)
    parser.add_argument('--build-dir', type=Path, required=True)
    parser.add_argument('--oet-root', type=Path, default=OET)
    parser.add_argument('--version', choices=['OET', 'OET-RV', 'OET-LV'], default='OET')
    args = parser.parse_args()
    selection = select_books(args)
    books, front = selected_content(args, selection)
    if front is None:
        parser.error('choose a collection or --front-matter')
    audit(args.pdf, args.build_dir, selection, books, front, args.start_books_on_odd_pages)
