# BibleTypesetter

Comparing [SILE](https://sile-typesetter.org/) and
[PTXPrint/XeTeX](https://software.sil.org/ptxprint/) for print and screen Bible PDFs.

[Ruth with SILE: print](SILE/OET-RUT.B5.print.pdf) · [screen](SILE/OET-RUT.B5.screen.pdf) · [Build the SILE edition](SILE/README.md)

[Ruth with PTXPrint: print](PTXPrint/OET-RUT.B5.print.pdf) · [screen](PTXPrint/OET-RUT.B5.screen.pdf) · [Build the PTXPrint edition](PTXPrint/README.md)

The ISO B5 Ruth proofs have 11 pages in SILE and 12 in PTXPrint.

## Publication profiles

The engines read publication data from TOML. The supplied
[SILE settings](SILE/settings.toml) and [PTXPrint settings](PTXPrint/settings.toml)
both extend [the OET profile](profiles/oet.toml). This keeps the two OET editions
consistent while allowing engine-specific overrides.

The shared profile contains the publication title and author, copyright and
licence wording, source root and filename patterns, edition IDs and labels,
reading URLs, preface source, external book-order/version settings, text
normalisation rules, alignment mappings, screen colours, and logo artwork.
The Python and rendering code consume those values. Existing internal names
such as `oet.lua` and `OET...` TeX commands are retained for compatibility;
they do not select the publication's identity or licence.

```sh
python3 SILE/typeset.py RUT --config SILE/settings.toml --screen
python3 PTXPrint/typeset.py RUT --config PTXPrint/settings.toml --print
python3 SILE/typeset.py MRK --config /path/to/another-publication.toml
```

`--config` selects the complete publication/layout profile. `--layout-settings`
remains an alias. `--source-root` overrides its source root (`--oet-root` is
retained as an alias). `--version` selects an edition ID declared in that
profile. Without it, `publication.default_version` is used. `--settings` can
still override a configured external order/version settings file.

Paths are relative to the TOML file that declares them, even when another
file extends it. Tables merge recursively. A local folio-only override should
therefore include `extends = "/path/to/the/engine/settings.toml"` before
`page_numbers = "centred"`.

For another translation, create a standalone profile. A minimal one-version
example is:

```toml
[publication]
id = "EXAMPLE"
title = "Example Bible"
default_version = "EXAMPLE"
author = "Example Publisher"
licence = "Your actual publication licence"
intro_licence = "{licence}"
copyright_paragraphs = ["{licence}"]

[editions.EXAMPLE]
sides = ["rv"]
label = "Example edition"

[sources]
root = "/path/to/USFM-files"
[sources.rv]
id = "EXAMPLE"
label = "Example edition"
patterns = ["{code}.usfm"]
```

`rv` and `lv` are the two internal source slots. A profile can use either
slot alone or both, with arbitrary edition names. Basic USFM/ESFM markers
are supported; this is not a new USX/OSIS importer. The OET join replacements,
editorial-code removal and BibleOrgSys mapping IDs are enabled by the OET
profile. They do not apply to an unrelated standalone profile. A preface,
logos, web links and release manifests are optional. For release manifests,
set `release_file` and, optionally, `release_resource` on the relevant source.

The publication templates can refer to other publication fields with
`{copyright}`, `{licence}`, `{licence_url}`, `{version}` and `{draft_credit}`.
The per-book reading URL uses `{code}`. `books.settings_keys` maps generic
order/version fields to names in an external settings file; it is parsed as
data without executing Python. A profile can instead supply `books.sequence`,
`books.aliases`, `books.dc_rv`, `books.dc_lv` and `publication.draft_version`
directly, with traditional book order available independently.

### Linked logos

The supplied profile points to the existing artwork under
`/srv/FreelyGiven/OpenEnglishTranslation-website/OET-Logo-Files/`.
`logos.opening` appears above the first-page title or on the title page,
`logos.ending` follows each book's closing material, and `logos.footer`
appears beside the folio area on ordinary pages. Blank versos stay blank;
the title page uses the large logo without a footer mark.

Each placement has `enabled`, `print`, `screen`, `href`, `height_pt` and
`max_width_pt` settings. Artwork keeps its aspect ratio. PNG is currently
supported by both renderers. Print uses the supplied black artwork, while
screen uses the wide colour logo and colour mark. Every displayed logo has
its configured live link. Disable the repeating mark with:

```toml
[logos.footer]
enabled = false
```

The artwork stays in its source folder. PTXPrint copies the selected images
into its build directory so retained builds are reproducible.

## Script versions and line breaking

Both drivers and the batch builder report `--script-version`; the shared
`PREPROCESSOR_VERSION` in `oet_publication.py` also appears in PDF credits.
Increment it whenever either toolchain changes. This layout and hyphenation
update is v1.1.0.

The OET parallel profile uses RV outside (53% width, 10.4/12.5 pt) and LV inside
(47% width, 9.4/11.25 pt). Matched section starts take priority over exact LV
front/back registration. `editions` tables set `primary_column`, `primary_width`,
`font_sizes` and `line_spacing`; each source sets `line_breaks` (`english`,
`underscore` or `none`). RV uses standard English hyphenation. LV breaks at an
underscore with `_` on both sides of the line break; `+`, `=` and `÷` become `_`.

## Building the complete SILE download catalogue

Run `python3 SILE/build_pdfs.py` to create print and screen PDFs for OT, NT,
DC & other, ALL, and every individual book. The supplied OET profile selects
OET book order, with parallel OET (84 books plus four collections) and OET-RV
(82 available books plus four collections). Each has B5, A4 and Letter print
PDFs and a B5 screen PDF, giving 696 downloads. Set `batch.versions`,
`batch.print_sizes` and `batch.screen_size` to change this matrix. Publication
paths and labels remain in `[batch]` in [profiles/oet.toml](profiles/oet.toml).

The PDFs, `manifest.json`, and an `index.htm` download page go directly into
`OpenBibleData/htmlPages/OET/Downloads/`. The generated links use
`https://Freely-Given.org/OBD/OET/Downloads/`. A small copy of the catalogue
goes into the OET website's `src/data/oet-pdfs.json`; its Downloads page uses
those external links, so no PDFs are included in the OET.Bible deployment.

The OET scripts makefile includes this batch in its default `ALL` target.
Use `make PDF` there to build only the PDF downloads and their source
prerequisites. PDF generation waits for RV linking and the OT, NT and DC
release writers even with parallel make. `TYPESETTER_DIR`, `PDF_CONFIG`,
`PDF_PYTHON` and `PDF_ARGS` can override the makefile defaults.

The batch checks content fingerprints of each book, release metadata, preface,
settings, artwork, renderer and mapping code. It skips unchanged PDFs, rebuilds
missing or damaged outputs, and preserves the previous PDF after a failed
render. Successful jobs are cached privately under `.build/sile-downloads/`,
so interrupted batches can resume. The public catalogues are updated only
after a complete successful batch. No network upload is performed.

Useful batch options:

```sh
python3 SILE/build_pdfs.py --list-targets
python3 SILE/build_pdfs.py --jobs 2
python3 SILE/build_pdfs.py --only RUT DC
python3 SILE/build_pdfs.py --force
```

`--only` refreshes every configured edition and size for selected targets and leaves catalogues alone;
run the full batch afterward to update both sites' listings. `--config`,
`--paper-size`, `--version`, `--output-dir`, `--cache-dir` and `--catalogue-file`
are also available. OBD preserves `OET/Downloads/` when replacing its generated
Bible pages. Commit the generated small JSON catalogue with the OET website;
publish the PDF folder through the normal OBD hosting process.

## Print or screen

Both scripts accept `--print` (the default) or `--screen`. These are mutually
exclusive command-line flags, independent of the layout TOML files.

```sh
python3 SILE/typeset.py RUT --screen
python3 PTXPrint/typeset.py RUT --print
```

Default names end in `.SIZE.print.pdf` or `.SIZE.screen.pdf`, for example
`OET-RUT.B5.print.pdf` and `OET-RUT.B5.screen.pdf`. An explicit `-o` remains exact.
Both outputs contain borderless, clickable web links. Print shows full URLs
including `https://`; screen omits that prefix from displayed URLs and colours
links blue. OET.Bible, the licence and project URLs, source hyperlinks, and URLs
in the preface and notes are included. Relative source links resolve to the
online OET book. Descriptive source links also show their destination in print.
The reading link immediately follows the toolchain credit: the final book's
online page for an edition without a cover, or the OET section directory on
the copyright page.

Screen adds green heading boxes and note calls, red verse numbers, purple
titles/headers, and brown for source-marked words of Jesus, using accents based
on the OBD OET stylesheet. Addition categories retain their existing grey
styling. Print remains greyscale. Fonts, paper, margins and baseline grid are
shared; longer visible URLs can change wrapping and pagination.
These web links do not add internal PDF bookmarks or verse navigation.

## Collections and book order

Both drivers accept `OT`, `DC`, `NT`, or `ALL`, either positionally or with
`--collection`. Collections include a title page, its copyright/licence verso,
a contents index with actual page numbers, and the complete Readers’ Version preface from `OET-RV_FRT.ESFM`,
followed by each book's introduction and text. The index can span several pages.

The title is **Open English Translation of the Bible**. Contents and preface
each start on a right-hand (odd-numbered) page; blank versos are inserted when
needed, without running heads or printed page numbers. The copyright page
includes the CC BY-SA 4.0 licence, attribution, project/source links and a short
description of the two versions, drawn from the OET website's licence and
overview pages. Its draft credit includes `OET_VERSION_NUMBER_STRING` read
from the same `settings.py` used for book order. Book introductions carry the
draft credit too, including single-book builds without a title page; the
overall title page does not show it. If no settings version is available,
the credit explicitly says so.

Each book ends with the RV revision from its ESFM `\id` and the LV set release
from the top-level `version` field in the `version.json` beside its LV source.
For Ruth the LV line reads `RUT · OET-LV v0.2.0 (OT set)`. If an LV source
also supplies its own book revision, that appears alongside the set release.
Older sources without a manifest use their ESFM ID revision when available.

The title is centred over two lines, “Open English Translation” above “of the Bible”.
A PDF without a title page opens with those lines above the first book.
Its final book ends with one full-width line giving the
preprocessing script and renderer versions. Publications with a title page put
this line on the copyright verso. In both layouts, printed LV text uses an
underscore for the source’s `+`, `=` and `÷` word joins.

Page numbers default to the outside edge (left on even pages, right on odd
pages). To centre them, set `page_numbers = "centred"` in
[SILE/settings.toml](SILE/settings.toml) or
[PTXPrint/settings.toml](PTXPrint/settings.toml). Both drivers also accept
`--layout-settings PATH` for a separate print configuration. The existing
`--settings` option selects the OpenBibleData book-order and draft settings.
Scripture pages show the chapter and verse range covered by the printed text.
The range includes both columns and any verse continuing across a page turn.

By default, each new book starts on the next available page. Add
`--start-books-on-odd-pages` to either driver to start every book's introduction
on a right-hand page. Inserted blanks count towards the index and preserve
the page grid and mirrored margins:

```sh
python3 SILE/typeset.py NT --start-books-on-odd-pages
python3 PTXPrint/typeset.py NT --start-books-on-odd-pages
```

```sh
python3 SILE/typeset.py NT --book-order oet --paper-size B5 -o sile-nt.pdf
python3 PTXPrint/typeset.py NT --book-order oet --paper-size B5 -o ptx-nt.pdf
python3 SILE/typeset.py OT --book-order traditional --version OET-RV --paper-size A4
python3 PTXPrint/typeset.py DC --book-order traditional --paper-size Letter
python3 SILE/typeset.py ALL --list-books
```

`--book-order oet` is the collection default. It reads the ordering, DC
membership and filename aliases directly from
`/srv/FreelyGiven/OpenBibleData/createPages/settings.py`; override that path
with `--settings`. The settings are parsed without executing the website code.
`traditional` uses English OT/NT order, with the KJV Apocrypha sequence followed
by the additional available DC books. In `ALL`, this DC sequence falls between
the OT and NT. OET order places Laodiceans after Colossians in `ALL`; it remains
part of the DC selection, while `NT` contains the usual 27 books.

The present sources supply 39 OT books, 27 NT books, 16 RV DC books and 17 LV
DC books (18 distinct DC books in paired OET). `ALL` consequently contains
84 books in OET, 82 in OET-RV, or 83 in OET-LV. Canonical `GES`, `LES` and
`DNG` also accept source aliases `ES1`, `ES2` and `DAG`, without duplicating books.

Paired DC output aligns **chapter starts only**, retaining each edition's
verse numbering and text order. Each DC introduction carries a notice that
corresponding lines are not established equivalents. A missing version or
chapter gets an explicit absence notice in that column. Single-version DC
collections include the books available in that version. OT and Acts pairing
uses BibleOrgSys's OET-RV/OET-LV verse mappings, preserving the printed source
numbers and marking a documented passage with no counterpart.

Individual book selections keep their supplied order unless `--book-order`
is given. Add `--front-matter` to give such a selection the same opening pages.
All collection options combine with `--version`, named or custom paper sizes,
`--build-dir`, and `--prepare-only`.

Default output filenames include the paper size: `OET-NT-oet.B5.print.pdf`,
`OET-RV-OT-traditional.A4.print.pdf`, or `OET-DC-traditional.Letter.print.pdf`.
Custom sizes use labels such as `.160x240mm.print.pdf`, `.6x9in.print.pdf`, or
`.8.5inx297mm.print.pdf` for mixed units. An explicit `-o` / `--output` filename
is used exactly as supplied.

Collection builds require Python 3.11+, Poppler's `pdfinfo` and `pdfunite`, and
the BibleOrgSys checkout beside this repository (or importable on `PYTHONPATH`)
for OT/Acts alignment. Both engines typeset each book separately to bound
memory use and isolate page-builder state. Page numbers and mirrored margins
remain continuous; finished pages are joined without scaling or rasterization.
The front matter is rendered again with the measured book starts. Notes restart
at 1 for each book. `--build-dir` retains each book's inputs, logs and proof,
plus `book-pages.tsv` for the publication.

PTXPrint checks every note against its caller's physical page. If native
page-builder retries duplicate or move a note, the driver automatically
uses measured note boxes and reserves whole grid rows for them on successive
passes. These conservative reserves can leave extra space above the notes.
The retained `note-pagination.json` records which books used this fallback.
LV words may break at any printed underscore, which is repeated at the start
of the next line without adding a hyphen.

Run checks with:

```sh
python3 -B -m unittest test_collections test_publication_links test_profiles
python3 -B -m unittest discover -s SILE
python3 -B -m unittest discover -s PTXPrint
```

With `pdfplumber` installed, check a built collection's title, copyright,
contents/preface parity, book revision lines, order, index destinations
and complete preface using `check_publication.py`, for example:

```sh
python3 check_publication.py NT --pdf sile-nt.pdf --build-dir /tmp/sile-nt
# Include --start-books-on-odd-pages to check that optional layout too.
```

Earlier B5 New Testament proofs had 683 pages (SILE) and 684 pages
(PTXPrint), with embedded fonts and checked index destinations and preface
text. Full source and page-layout audits also
cover demanding PTXPrint samples including Psalms (1,350 notes), Job, Second
Kings, Second Chronicles, Isaiah and Odes. Page counts depend on the source
checkout and chosen print profile; PTXPrint's conservative OT note reservations
can use more paper than the SILE compositor.
Earlier 84-book paired `ALL` proofs also passed ordering, index-destination and
complete-preface audits in both engines; every PTXPrint note was checked against
its caller's physical page before the parts were assembled. The updated front
matter was additionally checked with all 84 index entries at B5 and 6 × 9 inches.

## Why SILE

The TeX family of typesetting tools has been used for many decades,
especially with extensions for Unicode and other modern updates.

However, [according to](https://sile-typesetter.org/what-is-sile/#SILE_versus_TeX) the SILE authors,
SILE is better at grid typesetting
which is especially helpful for diglot Bibles (two versions typeset side-by-side).

Another option was the commercial/expensive InDesign program,
but we're open source promoters
(and there's people in poorer countries that would like to typeset their own Bibles),
so that's not even on our list.
(Also, even the SIL/UBS [Publishing Assistant](https://pubassist.paratext.org/) is not available to average Joe without a number of [approvals and registrations](https://pubassist.paratext.org/registration/).)

The newer SIL [PTXPrint](https://software.sil.org/ptxprint/) IS [open source](https://github.com/sillsdev/ptx2pdf) and freely available,
~but it does seem to require a [Paratext](https://paratext.org/) configuration file
to be in your [USFM](https://ubsicap.github.io/usfm/) folder.
(And although Paratext is advertised on their own site as a free download,
it's not really very useful unless you're an approved and registered user
with access to a decent set of Bible translation resources.)~

Finally, we like to support new and alternative solutions
and wanted to back the SILE project.

Here is also a good place to express our thanks and gratitude
to the main SILE programmers and other contributors to
[this project](https://github.com/sile-typesetter/sile).
We totally admire their skills at handling fonts
and the simple process of placing dots at the correct pixel address (joke)
as well as their generosity in giving their time and mental energy
as an open-licensed gift to the whole world.

## Features

PTXPrint has set a high-bar for automated Bible typesetters.
We'll see how many of them that we can match.

## USX Test Bibles

One of the problems for SILE typesetting experts in testing their system on complex Bibles
is access to [USX](https://ubsicap.github.io/usx/)
(XML form of [USFM](https://ubsicap.github.io/usfm/))
Bibles that can be used for testing.
Hence we provide a USX test data folder [here](USX_test_versions/)
with some sample open-licenced Bibles.

Also, since the Digital Bible Library uses USX files,
maybe some other test versions can be downloaded from [here](https://app.thedigitalbiblelibrary.org/entries/open_access_entries?type=text).
