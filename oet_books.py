"""Shared publication selection, using OET's live order without importing its website."""
import argparse
import ast
from dataclasses import dataclass
from pathlib import Path

SETTINGS = Path('/srv/FreelyGiven/OpenBibleData/createPages/settings.py')
OT = 'GEN EXO LEV NUM DEU JOS JDG RUT SA1 SA2 KI1 KI2 CH1 CH2 EZR NEH EST JOB PSA PRO ECC SNG ISA JER LAM EZE DAN HOS JOL AMO OBA JNA MIC NAH HAB ZEP HAG ZEC MAL'.split()
NT = 'MAT MRK LUK JHN ACT ROM CO1 CO2 GAL EPH PHP COL TH1 TH2 TI1 TI2 TIT PHM HEB JAM PE1 PE2 JN1 JN2 JN3 JDE REV'.split()
# KJV Apocrypha sequence, using whole Greek Esther/Daniel where supplied;
# remaining OET DC books follow it. This is an order, not a canon declaration.
DC = 'GES LES TOB JDT ESG WIS SIR BAR LJE DNG PAZ SUS BEL MAN MA1 MA2 MA3 MA4 PS2 PSS ODE LAO'.split()
TITLES = {'OT': 'Old Testament', 'DC': 'Deuterocanonical books', 'NT': 'New Testament', 'ALL': 'The Bible with deuterocanonical books'}


def read_orders(path=SETTINGS):
    tree = ast.parse(Path(path).read_text(encoding='utf-8'), filename=str(path))
    state = next((node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'State'), None)
    if state is None:
        raise ValueError(f'{path}: State class not found')
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
    names = {'OET_OT_BOOK_ORDER', 'OET_APOCRYPHA_BOOK_ORDER', 'OET_NT_BOOK_ORDER', 'OET_BOOK_ORDER',
             'OET_RV_DC_BOOK_LIST', 'OET_LV_DC_BOOK_LIST', 'OET_SOURCE_BOOK_ALIASES'}
    optional = {'OET_VERSION_NUMBER_STRING'}
    for node in state.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) and node.targets[0].id in names | optional:
            values[node.targets[0].id] = evaluate(node.value)
        elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            call = node.value
            if isinstance(call.func, ast.Attribute) and isinstance(call.func.value, ast.Name) and call.func.value.id == 'OET_BOOK_ORDER' and call.func.attr == 'insert':
                values['OET_BOOK_ORDER'].insert(*(evaluate(arg) for arg in call.args))
    if names - values.keys():
        raise ValueError(f'{path}: missing book-order settings: {sorted(names - values.keys())}')
    for name in names - {'OET_SOURCE_BOOK_ALIASES'}:
        if len(values[name]) != len(set(values[name])):
            raise ValueError(f'{path}: duplicate book in {name}')
    if 'OET_VERSION_NUMBER_STRING' in values and not isinstance(values['OET_VERSION_NUMBER_STRING'], str):
        raise ValueError(f'{path}: OET_VERSION_NUMBER_STRING must be a string')
    return values


def source_path(root, edition, code, aliases=None, required=True):
    identities = {code} | {alias for alias, canonical in (aliases or {}).items() if canonical == code}
    candidates = []
    for identity in identities:
        if edition == 'RV':
            candidates += list((root / 'translatedTexts/ReadersVersion').glob(f'OET-RV_{identity}.ESFM'))
        else:
            for path in (root / 'derivedTexts').glob(f'*/OET-LV_{identity}.ESFM'):
                if path.parent.match('auto_edited_*_ESFM') or path.with_name('version.json').is_file():
                    candidates.append(path)
    if len(candidates) > 1 or (required and not candidates):
        raise ValueError(f'expected one OET-{edition} ESFM source for {code}, found {len(candidates)}')
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

    @property
    def title(self):
        return TITLES.get(self.collection, 'Selected books')

    @property
    def stem(self):
        return f'{self.collection}-{self.order}' if self.collection else '-'.join(self.codes)


def selection_arguments(parser):
    parser.add_argument('books', nargs='*', help='book codes, or OT, DC, NT or ALL (default: MRK)')
    parser.add_argument('--collection', type=str.upper, choices=tuple(TITLES), help='select a complete set instead of individual books')
    parser.add_argument('--book-order', type=str.lower, choices=('oet', 'traditional'), help='OET (collection default), or traditional English/KJV order')
    parser.add_argument('--settings', type=Path, default=SETTINGS, help='OpenBibleData settings.py defining OET book order, aliases and draft version')
    parser.add_argument('--front-matter', action='store_true', help='also add title, copyright, contents and RV preface to an individual-book selection')
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
    # Explicit MRK builds remain independent of the website checkout.
    config = read_orders(args.settings) if collection or args.book_order or Path(args.settings).is_file() else None
    aliases = config['OET_SOURCE_BOOK_ALIASES'] if config else {}
    dc = set(config['OET_RV_DC_BOOK_LIST'] + config['OET_LV_DC_BOOK_LIST']) if config else set(DC)
    order = args.book_order or ('oet' if collection else 'given')
    if collection:
        dc_members = set(config['OET_RV_DC_BOOK_LIST'] if args.version == 'OET-RV' else config['OET_LV_DC_BOOK_LIST'] if args.version == 'OET-LV' else dc)
        members = {'OT': set(OT), 'NT': set(NT), 'DC': dc_members, 'ALL': set(OT + NT) | dc_members}[collection]
        sequence = config['OET_BOOK_ORDER'] if order == 'oet' else OT + DC + NT
        codes = [c for c in sequence if c in members]
        if set(codes) != members:
            raise ValueError(f'{order} order omits selected books: {sorted(members - set(codes))}')
    else:
        codes = [aliases.get(c, c) for c in codes or ['MRK']]
        if args.book_order:
            sequence = config['OET_BOOK_ORDER'] if order == 'oet' else OT + DC + NT
            if set(codes) - set(sequence):
                raise ValueError('one or more selected books are absent from the chosen order')
            codes = sorted(codes, key=sequence.index)
    if any(len(c) != 3 or not c.isalnum() for c in codes) or len(set(codes)) != len(codes):
        raise ValueError('use distinct three-character book codes, e.g. MRK JN2')
    return Selection(codes, collection, order, bool(collection or args.front_matter), aliases, dc,
                     config.get('OET_VERSION_NUMBER_STRING') if config else None)
