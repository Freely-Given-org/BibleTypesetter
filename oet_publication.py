"""Publication filenames and lossless assembly with continuous folios."""
import os
import re
import shutil
import subprocess

TITLE = 'Open English Translation of the Bible'
# Publication wording distilled from the local OET website's
# src/pages/About/Licence.astro and src/pages/Intro/Overview.astro (2026-11-05).
COPYRIGHT = 'Copyright © 2010-2026 Freely-Given.org.'
LICENCE = 'Creative Commons Attribution-ShareAlike 4.0 International (CC BY-SA 4.0)'


def draft_credit(version):
    draft = f'Translation draft {version}' if version else 'Translation draft (version unavailable)'
    return f'Open English Translation · {draft} · OET.Bible'


def copyright_paragraphs(version):
    return [draft_credit(version), COPYRIGHT,
            f'This translation is made available under the {LICENCE} licence.',
            'You may copy, share and print this translation under that licence. '
            'Preserve its copyright and attribution, and share adaptations under the same licence. '
            'The OET publication guidelines ask that an adapted translation use a different name.',
            'Licence: https://creativecommons.org/licenses/by-sa/4.0/',
            'The Readers’ Version presents the meaning in modern English. The Literal Version helps '
            'readers examine the wording of the source languages. The two versions are designed to be read together.',
            'This translation is still a draft. The overall draft version is shown above; '
            'the end of each book shows the Readers’ Version book revision or the Literal Version set release, '
            'or both in the parallel edition.',
            'Project and publication guidelines: https://OpenEnglishTranslation.Bible/About/Licence',
            'Source files: https://github.com/Freely-Given-org/OpenEnglishTranslation--OET']


def book_version_labels(book):
    sides = ('rv', 'lv') if book.get('version') == 'OET' else (book.get('version')[-2:].lower(),)
    labels = {}
    for side in sides:
        source_version = book.get(side + '-source-version')
        value = ('source unavailable' if source_version is None else
                 source_version or 'version not specified in source ID')
        release = book.get(side + '-set-release')
        if release:
            value = release
            if source_version:
                value += f' · book {source_version}'
        labels[side] = f"{book.get('code')} · OET-{side.upper()} {value}"
    return labels


def default_pdf_filename(version, stem, size):
    """Include a readable paper label, using the driver's parsed paper size."""
    label = {'b5': 'B5', 'a4': 'A4', 'letter': 'Letter'}.get(size)
    if label is None:
        width, height = size.split(' x ')
        # Share the unit for matching dimensions; retain both for mixed units.
        label = (width[:-2] if width[-2:] == height[-2:] else width) + 'x' + height
    return f'{version}-{stem}.{label}.pdf'


def require_poppler():
    if not shutil.which('pdfunite') or not shutil.which('pdfinfo'):
        raise ValueError('Collection builds require pdfinfo and pdfunite (poppler-utils).')


def pdf_pages(path):
    result = subprocess.run(['pdfinfo', str(path)], capture_output=True, text=True,
                            env={**os.environ, 'LC_ALL': 'C'}, check=True)
    match = re.search(r'^Pages:\s+(\d+)', result.stdout, re.MULTILINE)
    if not match:
        raise ValueError(f'Cannot read the page count of {path}')
    return int(match[1])


def merge_parts(parts, output):
    subprocess.run(['pdfunite', *map(str, parts), str(output)], check=True,
                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
