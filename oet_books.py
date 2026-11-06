"""Book selection and source discovery driven by a publication profile."""
import argparse
import ast
from dataclasses import dataclass
from pathlib import Path

from publication_config import default_profile

SETTINGS = default_profile().settings_file
OT = 'GEN EXO LEV NUM DEU JOS JDG RUT SA1 SA2 KI1 KI2 CH1 CH2 EZR NEH EST JOB PSA PRO ECC SNG ISA JER LAM EZE DAN HOS JOL AMO OBA JNA MIC NAH HAB ZEP HAG ZEC MAL'.split()
NT = 'MAT MRK LUK JHN ACT ROM CO1 CO2 GAL EPH PHP COL TH1 TH2 TI1 TI2 TIT PHM HEB JAM PE1 PE2 JN1 JN2 JN3 JDE REV'.split()
# KJV Apocrypha sequence, using whole Greek Esther/Daniel where supplied;
# remaining OET DC books follow it. This is an order, not a canon declaration.
DC = 'GES LES TOB JDT ESG WIS SIR BAR LJE DNG PAZ SUS BEL MAN MA1 MA2 MA3 MA4 PS2 PSS ODE LAO'.split()
TITLES = {'OT': 'Old Testament', 'DC': 'Deuterocanonical books', 'NT': 'New Testament', 'ALL': 'The Bible with deuterocanonical books'}


def read_orders(path=None, profile=None):
    profile = profile or default_profile()
    path = path or profile.settings_file
    keys = profile.data.get('books', {}).get('settings_keys', {})
    state_name = profile.data.get('books', {}).get('settings_class', 'State')
    tree = ast.parse(Path(path).read_text(encoding='utf-8'), filename=str(path))
    state = next((node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == state_name), None)
    if state is None:
        raise ValueError(f'{path}: {state_name} class not found')
    values = {}
    def evaluate(node):
        if isinstance(node, (ast.List, ast.Tuple)):
            return [evaluate(item) for item in node.elts]
        if isinstance(node, ast.Dict):
            return dict(zip(map(evaluate, node.keys), map(evaluate, node.values)))
        if isinstance(node, ast.Constant) and isinstance(node.value, (str, int)):
            return node.value
        if isinstance(node, ast.Name) and node.id in values:
            return values[node.id]
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            return evaluate(node.left) + evaluate(node.right)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'index':
            return evaluate(node.func.value).index(evaluate(node.args[0]))
        raise ValueError(f'{path}: unsupported book-order expression: {ast.unparse(node)}')
    optional = {keys['draft_version']} if 'draft_version' in keys else set()
    names = set(keys.values()) - optional
    for node in state.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) and node.targets[0].id in names | optional:
            values[node.targets[0].id] = evaluate(node.value)
        elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            call = node.value
            if isinstance(call.func, ast.Attribute) and isinstance(call.func.value, ast.Name) and call.func.value.id == keys.get('sequence') and call.func.attr == 'insert':
                values[keys['sequence']].insert(*(evaluate(arg) for arg in call.args))
    if names - values.keys():
        raise ValueError(f'{path}: missing book-order settings: {sorted(names - values.keys())}')
    for name in names - {keys.get('aliases')}:
        if len(values[name]) != len(set(values[name])):
            raise ValueError(f'{path}: duplicate book in {name}')
    version_key = keys.get('draft_version')
    if version_key in values and not isinstance(values[version_key], str):
        raise ValueError(f'{path}: {version_key} must be a string')
    return values


def source_path(root, edition, code, aliases=None, required=True, profile=None):
    profile = profile or default_profile()
    source = profile.source(edition)
    identities = {code} | {alias for alias, canonical in (aliases or {}).items() if canonical == code}
    candidates = sorted({p for identity in identities for pattern in source['patterns']
                         for p in Path(root).glob(pattern.format(code=identity)) if p.is_file()})
    if len(candidates) > 1 or (required and not candidates):
        raise ValueError(f'expected one {source["id"]} source for {code}, found {len(candidates)}')
    return candidates[0] if candidates else None


@dataclass
class Selection:
    codes: list
    collection: str | None
    order: str
    front: bool
    aliases: dict
    dc: set
    draft_version: str | None = None
    collection_title: str | None = None

    @property
    def title(self):
        return self.collection_title or TITLES.get(self.collection, 'Selected books')

    @property
    def stem(self):
        return f'{self.collection}-{self.order}' if self.collection else '-'.join(self.codes)


def selection_arguments(parser):
    parser.add_argument('books', nargs='*', help='book codes, or OT, DC, NT or ALL (default from TOML)')
    parser.add_argument('--collection', type=str.upper, choices=tuple(TITLES), help='select a complete set instead of individual books')
    parser.add_argument('--book-order', type=str.lower, help='profile-defined order name, or traditional English/KJV order')
    parser.add_argument('--settings', type=Path, help='override the profile’s external order/version settings file')
    parser.add_argument('--front-matter', action='store_true', help='also add title, copyright, contents and configured preface to an individual-book selection')
    parser.add_argument('--start-books-on-odd-pages', action='store_true',
                        help='start every book on a right-hand page, inserting blank versos as needed (default: off)')
    parser.add_argument('--list-books', action='store_true', help='show selected canonical book codes without typesetting')


def select_books(args):
    codes = [c.upper() for c in args.books]
    collection = args.collection
    if len(codes) == 1 and codes[0] in TITLES:
        if collection:
            raise ValueError('specify a collection only once')
        collection, codes = codes[0], []
    if collection and codes:
        raise ValueError('a collection cannot be combined with individual book codes')
    profile = getattr(args, 'profile', None) or default_profile()
    settings = args.settings or profile.settings_file
    book_config = profile.data.get('books', {})
    keys = book_config.get('settings_keys', {})
    raw = read_orders(settings, profile) if settings and Path(settings).is_file() else {}
    config = {name: raw[key] for name, key in keys.items() if key in raw}
    aliases = config.get('aliases', book_config.get('aliases', {}))
    dc = set(config.get('dc_rv', book_config.get('dc_rv', DC)) + config.get('dc_lv', book_config.get('dc_lv', DC)))
    order = args.book_order or (book_config.get('collection_order', 'traditional') if collection else 'given')
    custom_order = book_config.get('order_name', 'custom')
    if order not in ('given', 'traditional', custom_order):
        raise ValueError(f'unknown book order {order!r}; choose {custom_order} or traditional')
    sequence = config.get('sequence', book_config.get('sequence')) if order == custom_order else OT + DC + NT
    if order == custom_order and not sequence:
        raise ValueError(f'{profile.path}: the {custom_order} sequence requires its configured settings file or books.sequence')
    sides = profile.sides(args.version)
    if collection:
        dc_members = set(config.get('dc_' + sides[0], book_config.get('dc_' + sides[0], DC))) if len(sides) == 1 else dc
        members = {'OT': set(OT), 'NT': set(NT), 'DC': dc_members, 'ALL': set(OT + NT) | dc_members}[collection]
        codes = [c for c in sequence if c in members]
        if set(codes) != members:
            raise ValueError(f'{order} order omits selected books: {sorted(members - set(codes))}')
    else:
        codes = [aliases.get(c, c) for c in codes or book_config.get('default', ['GEN'])]
        if args.book_order:
            if set(codes) - set(sequence):
                raise ValueError('one or more selected books are absent from the chosen order')
            codes = sorted(codes, key=sequence.index)
    if any(len(c) != 3 or not c.isalnum() for c in codes) or len(set(codes)) != len(codes):
        raise ValueError('use distinct three-character book codes, e.g. MRK JN2')
    return Selection(codes, collection, order, bool(collection or args.front_matter), aliases, dc,
                     config.get('draft_version', profile.publication.get('draft_version')),
                     book_config.get('collection_titles', {}).get(collection))
