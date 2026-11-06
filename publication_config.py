"""Publication profiles for both typesetters; no translation-specific defaults.

Paths belong to the TOML file declaring them. An engine settings file can
extend a publication profile and override individual values recursively.
"""
from copy import deepcopy
from dataclasses import dataclass
from functools import lru_cache
import math
from pathlib import Path
import re
import struct
import tomllib


def _merge(base, override):
    result = deepcopy(base)
    for key, value in override.items():
        result[key] = _merge(result[key], value) if isinstance(value, dict) and isinstance(result.get(key), dict) else deepcopy(value)
    return result


def _read(path, parents=()):
    path = Path(path).expanduser().resolve()
    if path in parents:
        raise ValueError(f'{path}: cyclic TOML inheritance')
    with path.open('rb') as stream:
        try:
            data = tomllib.load(stream)
        except tomllib.TOMLDecodeError as error:
            raise ValueError(f'{path}: {error}') from error
    def resolve(value):
        p = Path(value).expanduser()
        return str((path.parent / p).resolve())
    for table, key in [('sources', 'root'), ('books', 'settings_file'), ('tools', 'ptxprint_root'),
                       ('batch', 'output_dir'), ('batch', 'cache_dir'), ('batch', 'catalogue_file')]:
        if data.get(table, {}).get(key):
            data[table][key] = resolve(data[table][key])
    for logo in data.get('logos', {}).values():
        for medium in ('print', 'screen'):
            if logo.get(medium):
                logo[medium] = resolve(logo[medium])
    parent = data.pop('extends', None)
    return _merge(_read(path.parent / parent, (*parents, path)), data) if parent else data


@dataclass
class Profile:
    path: Path
    data: dict

    @property
    def publication(self):
        return self.data['publication']

    @property
    def title(self):
        return self.publication['title']

    @property
    def version(self):
        return self.publication['default_version']

    @property
    def source_root(self):
        return Path(self.data['sources']['root'])

    @property
    def settings_file(self):
        value = self.data.get('books', {}).get('settings_file')
        return Path(value) if value else None

    @property
    def page_numbers(self):
        value = self.data.get('page_numbers', 'outside')
        return 'centred' if value == 'centered' else value

    def sides(self, version=None):
        version = version or self.version
        try:
            return self.data['editions'][version]['sides']
        except KeyError as error:
            raise ValueError(f'{self.path}: unknown edition {version!r}; choose {", ".join(self.data["editions"])}') from error

    def source(self, side):
        return self.data['sources'][side.lower()]

    def reading_url(self, code=None):
        value = self.publication.get('reading_url' if code else 'collection_url', '')
        return value.format(code=code) if value else ''

    def format(self, text, version=None):
        values = {**self.publication, 'version': version or '(version unavailable)'}
        try:
            values['draft_credit'] = self.publication.get('draft_template', '').format_map(values)
            return text.format_map(values)
        except (KeyError, ValueError, IndexError) as error:
            raise ValueError(f'{self.path}: invalid publication text template: {error}') from error

    def renderer_attributes(self, version):
        sides = self.sides(version)
        attrs = {'version': version, 'sides': ' '.join(sides),
                 'publication-title': ' '.join(self.title.splitlines()),
                 'publication-author': self.publication.get('author', ''),
                 'running-title': self.publication.get('running_title', self.publication['id']),
                 'edition-title': self.data['editions'][version].get('label', version),
                 'copyright-heading': self.publication.get('copyright_heading', 'Publication information')}
        for side in sides:
            source = self.source(side)
            attrs[side + '-id'] = source['id']
            attrs[side + '-label'] = source.get('label', source['id'])
        for key, value in self.data.get('screen_colours', {}).items():
            attrs['colour-' + key] = value
        return attrs

    def logo_attributes(self, medium):
        attrs = {}
        for role, logo in self.data.get('logos', {}).items():
            if not logo.get('enabled', False):
                continue
            source = Path(logo[medium])
            with source.open('rb') as stream:
                header = stream.read(24)
            if len(header) < 24 or header[:8] != b'\x89PNG\r\n\x1a\n':
                raise ValueError(f'{source}: logos currently require PNG artwork')
            w, h = struct.unpack('>II', header[16:24])
            if not w or not h:
                raise ValueError(f'{source}: invalid PNG dimensions')
            scale = min(logo['height_pt'] / h, logo['max_width_pt'] / w)
            for name, value in {'src': source, 'width': w * scale, 'height': h * scale,
                                'href': logo.get('href', '')}.items():
                attrs[f'logo-{role}-{name}'] = str(value)
        return attrs


def load_profile(path):
    path = Path(path).resolve()
    data = _read(path)
    profile = Profile(path, data)
    if profile.page_numbers not in ('outside', 'centred'):
        raise ValueError(f'{path}: page_numbers must be "outside" or "centred"')
    for table in ('publication', 'sources', 'editions'):
        if not isinstance(data.get(table), dict):
            raise ValueError(f'{path}: missing [{table}] table')
    for key in ('id', 'title', 'default_version'):
        if not isinstance(profile.publication.get(key), str) or not profile.publication[key]:
            raise ValueError(f'{path}: publication.{key} must be a nonempty string')
    if not data['sources'].get('root'):
        raise ValueError(f'{path}: sources.root is required')
    for name, edition in data['editions'].items():
        if not re.fullmatch(r'[A-Za-z0-9_-]+', name):
            raise ValueError(f'{path}: invalid edition name {name!r}')
        sides = edition.get('sides')
        if sides not in (['rv'], ['lv'], ['rv', 'lv']):
            raise ValueError(f'{path}: {name}.sides must select rv, lv or both in that order')
        for side in sides:
            source = data['sources'].get(side, {})
            if not source.get('id') or not isinstance(source.get('patterns'), list) or not source['patterns']:
                raise ValueError(f'{path}: sources.{side} requires an id and source patterns')
            if any('{code}' not in p for p in source['patterns']):
                raise ValueError(f'{path}: source patterns must contain {{code}}')
            if any(len(k) != 1 for k in source.get('text_replacements', {})):
                raise ValueError(f'{path}: text_replacements keys must be single characters')
    profile.sides()
    for name, colour in data.get('screen_colours', {}).items():
        if not isinstance(colour, str) or not re.fullmatch('[0-9A-Fa-f]{6}', colour):
            raise ValueError(f'{path}: screen_colours.{name} must be six hexadecimal digits')
    for role, logo in data.get('logos', {}).items():
        if role not in ('opening', 'ending', 'footer'):
            raise ValueError(f'{path}: unknown logo placement {role!r}')
        if not logo.get('enabled', False):
            continue
        for key in ('height_pt', 'max_width_pt'):
            value = logo.get(key)
            if not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise ValueError(f'{path}: logos.{role}.{key} must be positive')
        if role == 'footer' and logo['height_pt'] > 12.5:
            raise ValueError(f'{path}: footer logo must fit within one 12.5pt grid row')
        if not all(logo.get(k) for k in ('print', 'screen')):
            raise ValueError(f'{path}: enabled logos need print and screen artwork')
        if logo.get('href') and not logo['href'].startswith(('https://', 'http://')):
            raise ValueError(f'{path}: logo links must be web URLs')
    return profile


@lru_cache(maxsize=1)
def default_profile():
    """Compatibility for parser callers; CLI drivers always pass their profile."""
    return load_profile(Path(__file__).parent / 'SILE/settings.toml')


def profile_arguments(parser, directory):
    parser.add_argument('--config', '--layout-settings', dest='layout_settings', type=Path,
                        default=directory / 'settings.toml', help='publication/layout TOML (default: settings.toml beside this script)')


def resolve_arguments(args):
    args.profile = load_profile(args.layout_settings)
    args.version = args.version or args.profile.version
    # Accept the familiar case-insensitive spelling while preserving profile IDs.
    args.version = next((v for v in args.profile.data['editions'] if v.lower() == args.version.lower()), args.version)
    args.profile.sides(args.version)
    args.oet_root = args.oet_root or args.profile.source_root
    args.settings = args.settings or args.profile.settings_file
    return args.profile
