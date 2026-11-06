"""Shared publication details, print/screen links and lossless PDF assembly."""
import os
import re
import shutil
import subprocess
import tomllib
import xml.etree.ElementTree as ET
from urllib.parse import urljoin

from publication_config import default_profile

# Compatibility exports are read from TOML, never publication literals.
PRINT_TITLE = default_profile().title
TITLE = ' '.join(PRINT_TITLE.splitlines())
PREPROCESSOR_VERSION = '1.1.0'
COPYRIGHT = default_profile().publication.get('copyright', '')
LICENCE = default_profile().publication.get('licence', '')
SCREEN_COLOURS = default_profile().data.get('screen_colours', {})
URL = re.compile(r'''(?ix)(?<![\w@])(?:https?://[^\s<>"“”‘’]+|(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,63}(?![\w-])(?:/[^\s<>"“”‘’]*)?)''')


def output_arguments(parser):
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--print', dest='medium', action='store_const', const='print',
                       help='greyscale with full visible URLs (default)')
    group.add_argument('--screen', dest='medium', action='store_const', const='screen',
                       help='colour accents and links with shortened visible URLs')
    parser.set_defaults(medium='print')


def reading_url(code=None, profile=None):
    return (profile or default_profile()).reading_url(code)


def url_matches(text):
    """Leave sentence punctuation and enclosing parentheses outside a URL."""
    for match in URL.finditer(text):
        value = match.group().rstrip('.,;:!?')
        while value.endswith((')', ']')) and (
                value.count(value[-1]) > value.count('(' if value[-1] == ')' else '[')):
            value = value[:-1]
        yield match.start(), match.start() + len(value), value


def linked_runs(text, medium='print', attributes=None, base_url=None):
    attributes = dict(attributes or {})
    href = attributes.pop('href', None)

    def run(value, target=None):
        node = ET.Element('run', attributes)
        if target:
            node.set('href', target)
        node.text = value
        return node

    if href:
        target = urljoin(base_url or '', href)
        if not target.startswith(('https://', 'http://')):
            return [run(text)]
        matches = list(url_matches(text))
        is_url = len(matches) == 1 and matches[0][:2] == (0, len(text))
        if is_url:
            label = re.sub(r'^https?://', '', text, flags=re.I)
            if medium == 'print':
                label = (re.match(r'https?://', target)[0]) + label
        else:
            label = text + (f' ({target})' if medium == 'print' else '')
        return [run(label, target)]
    result, offset = [], 0
    for start, end, value in url_matches(text):
        if start > offset:
            result.append(run(text[offset:start]))
        target = value if re.match(r'https?://', value, re.I) else 'https://' + value
        label = re.sub(r'^https?://', '', value, flags=re.I) if medium == 'screen' else target
        result.append(run(label, target))
        offset = end
    if offset < len(text):
        result.append(run(text[offset:]))
    return result


def link_publication(root, medium, base_url=None):
    """Format visible URLs once, keeping the full destination in every run."""
    for parent in root.iter():
        for child in list(parent):
            if child.tag == 'run':
                position = list(parent).index(child)
                parent.remove(child)
                for i, node in enumerate(linked_runs(child.text or '', medium, child.attrib, base_url)):
                    parent.insert(position + i, node)


def book_credits(book, profile=None):
    profile = profile or default_profile()
    credits = ET.Element('credits')
    paragraphs = [('legend', text) for text in profile.publication.get('legend', [])]
    paragraphs += [('draft', book.get('draft-credit', draft_credit(None, profile))),
                   ('licence', profile.format(profile.publication.get('intro_licence', '')))]
    for kind, text in paragraphs:
        if text:
            ET.SubElement(ET.SubElement(credits, 'intro', kind=kind), 'run').text = text
    return credits


def toolchain_credit(engine):
    return f'Text preprocessed by script v{PREPROCESSOR_VERSION}, then PDF produced by {engine}'


def read_page_numbers(path):
    """Read folio placement from the selected toolchain's layout settings."""
    with path.open('rb') as stream:
        try:
            settings = tomllib.load(stream)
        except tomllib.TOMLDecodeError as error:
            raise ValueError(f'{path}: {error}') from error
    position = settings.get('page_numbers', 'outside')
    if position == 'centered':
        position = 'centred'
    if position not in ('outside', 'centred'):
        raise ValueError(f'{path}: page_numbers must be "outside" or "centred"')
    return position


def draft_credit(version, profile=None):
    profile = profile or default_profile()
    return profile.format(profile.publication.get('draft_template', ''), version)


def copyright_paragraphs(version, profile=None):
    profile = profile or default_profile()
    return [profile.format(text, version) for text in profile.publication.get('copyright_paragraphs', [])]


def book_version_labels(book):
    sides = book.get('sides', 'rv lv').split()
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
        labels[side] = f"{book.get('code')} · {book.get(side + '-id', side.upper())} {value}"
    return labels


def default_pdf_filename(version, stem, size, medium='print'):
    """Include the parsed paper size and the selected print/screen medium."""
    label = {'b5': 'B5', 'a4': 'A4', 'letter': 'Letter'}.get(size)
    if label is None:
        width, height = size.split(' x ')
        # Share the unit for matching dimensions; retain both for mixed units.
        label = (width[:-2] if width[-2:] == height[-2:] else width) + 'x' + height
    return f'{version}-{stem}.{label}.{medium}.pdf'


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
