# BibleTypesetter

Comparing [SILE](https://sile-typesetter.org/) and
[PTXPrint/XeTeX](https://software.sil.org/ptxprint/) for printed Bible PDFs.

[Ruth in the parallel Open English Translation (PDF)](SILE/OET-RUT.B5.pdf) · [Build the SILE edition](SILE/README.md)

[Ruth using PTXPrint/XeTeX (PDF)](PTXPrint/OET-RUT.B5.pdf) · [Build the PTXPrint edition](PTXPrint/README.md)

The ISO B5 Ruth proofs have 11 pages in SILE and 12 in PTXPrint.

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

Default output filenames include the paper size: `OET-NT-oet.B5.pdf`,
`OET-RV-OT-traditional.A4.pdf`, or `OET-DC-traditional.Letter.pdf`.
Custom sizes use labels such as `.160x240mm.pdf`, `.6x9in.pdf`, or
`.8.5inx297mm.pdf` for mixed units. An explicit `-o` / `--output` filename
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
Very long LV word joins get last-resort line breaks at their visible `_`, `÷`
or `=` separators if the native line breaker reports an overflow; the symbols
and text remain intact.

Run checks with:

```sh
python3 -B -m unittest test_collections
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
