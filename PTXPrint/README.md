# Printing the OET with PTXPrint/XeTeX

[Open the B5 Ruth print proof](OET-RUT.B5.print.pdf) or [screen proof](OET-RUT.B5.screen.pdf). This is the PTXPrint counterpart to the
[SILE prototype](../SILE/README.md): the same ESFM sources, matched RV/LV
sections, right-side inset RV headings, page-bottom notes, and a shared
recto-verso baseline grid.

## Build

[settings.toml](settings.toml) extends [the shared OET profile](../profiles/oet.toml)
and sets page numbers to `"outside"` by default. It supplies the publication's
sources, wording, licence, colours and linked logos. Use `--config PATH` for
another publication profile (`--layout-settings` remains an alias).
Set `page_numbers = "centred"` to centre folios.
See [publication profiles and logo settings](../README.md#publication-profiles). Scripture headers show the range of text on that
page, including verses that continue from the previous page. The retained
`proof.oetrefs` records the printed folios used to build each range.

Use Python 3.11 or newer, XeTeX, `xdvipdfmx`, and a PTXPrint source checkout or
installed macro directory. On Ubuntu/Debian the TeX tools are supplied by:

```sh
sudo apt install --no-install-recommends texlive-xetex poppler-utils
```

The proof uses **Gentium Plus**, **Lato**, **DejaVu Sans**, and **Ezra SIL** (Hebrew notes). PTXPrint also
requires **Source Code Pro** during startup. When using its source checkout,
the driver makes the bundled `fonts/` directory available to Fontconfig for
that build, without installing fonts or changing the system configuration.

From the BibleTypesetter root:

```sh
python3 PTXPrint/typeset.py RUT -o PTXPrint/OET-RUT.B5.print.pdf
python3 PTXPrint/typeset.py JN2 PHM -o letters.pdf
```

MRK is the default. The source checkout comes from `sources.root` in TOML; override it with
`--source-root` (or the older `--oet-root` alias).
PTXPrint is discovered at this machine's source checkout,
`/srv/Programming/ExternalPrograms/SIL_LSDev/ptx2pdf`, as configured by `tools.ptxprint_root` in TOML, or at
`/usr/share/ptx2pdf` or `/usr/local/share/ptx2pdf`. Use `--ptxprint-root PATH`
or `PTXPRINT_ROOT` elsewhere. `--xetex` / `XETEX_BIN` and `--xdvipdfmx` /
`XDVIPDFMX_BIN` override the executables found on PATH.

Both drivers support `OT`, `DC`, `NT`, and `ALL` collections, with
`--book-order oet|traditional`. Collection output begins with a title page,
its copyright/licence verso, a contents index containing actual book page
numbers, and the RV preface from FRT. Contents and preface start on right-hand
pages. Add `--start-books-on-odd-pages` for right-hand starts for every book
too (off by default). See [shared collection options](../README.md#collections-and-book-order)
for membership, aliases, chapter-level DC pairing and BibleOrgSys verse mappings.

```sh
python3 PTXPrint/typeset.py NT --book-order oet --build-dir /tmp/ptx-nt -o OET-NT.pdf
python3 PTXPrint/typeset.py ALL --book-order traditional --version OET-RV --paper-size Letter
python3 PTXPrint/typeset.py DC --list-books
```

This uses **PTXPrint's actual TeX macros directly**, driven by Python. It does
not require its GUI, Python application dependencies, or a Paratext project.
Keep the repository's `SILE/` directory alongside `PTXPrint/`: both drivers
deliberately share the ESFM parser in `SILE/typeset.py`.

## Print or screen

Use `--print` (default) for greyscale with full visible URLs, or `--screen`
for coloured headings, verse numbers and links with shortened URL labels.
Both have live web links, including the reading link after the toolchain credit.
For example, `python3 PTXPrint/typeset.py RUT --screen` creates
`OET-RUT.B5.screen.pdf`. These are CLI flags, not TOML settings.
See [shared output options](../README.md#print-or-screen).

## Paper and version

The options are the same as the SILE driver:

```sh
python3 PTXPrint/typeset.py MRK --paper-size B5
python3 PTXPrint/typeset.py MRK --paper-size A4 -o mark-a4.pdf
python3 PTXPrint/typeset.py MRK --paper-size Letter -o mark-letter.pdf
python3 PTXPrint/typeset.py MRK --paper-size "160x240mm" -o mark-custom.pdf
python3 PTXPrint/typeset.py MRK --paper-size "6 x 9 inches" -o mark-six-by-nine.pdf
python3 PTXPrint/typeset.py MRK --version OET-RV --paper-size A4
python3 PTXPrint/typeset.py MRK --version OET-LV --paper-size "8.5x11in"
```

`B5` means ISO B5, 176 × 250 mm. `Letter` means 8.5 × 11 inches. Custom sizes
are width × height; units may be shared or supplied for each dimension, for
example `"210mm x 297mm"`. Names are case-insensitive. The default version is
`OET`, with RV in the wider outside column and LV in the narrower inside
column (53:47). RV uses 10.4 pt type on 12.5 pt leading, while LV uses
9.4 pt type on 11.25 pt leading. Section starts remain aligned; LV register
matching is approximate. `OET-RV` has a full-width introduction followed by
two-column scripture; `OET-LV` retains one full-width column. Both load only
their own source. Default output names
are `VERSION-BOOKS.SIZE.print.pdf`, for example `OET-NT-oet.B5.print.pdf`,
`OET-MRK.A4.print.pdf`, `OET-MRK.Letter.print.pdf`, or `OET-MRK.160x240mm.print.pdf`.
Inch dimensions use labels such as `.6x9in.print.pdf`; mixed units retain both,
such as `.8.5inx297mm.print.pdf`. An explicit `-o` filename is used exactly as supplied.

Fonts, grid spacing and margins retain their physical size as paper changes.
Very small pages that cannot accommodate the layout are rejected.

The LV joins `+`, `=` and `÷` are printed as underscores. A line may break
at an underscore, retaining it at the line end and repeating it at the start
of the next line. No hyphen is inserted there. RV uses English hyphenation.
These source rules and the parallel edition’s fonts, spacing and column
placement are configured in the shared TOML profile.

## Layout and implementation

- [typeset.py](typeset.py) converts the shared parser's structured text to
  USFM, with a native diglot chunk for each RV section. Exact verse addresses
  align the sections, including RV verse bridges. The versions then flow
  independently until the next section, potentially leaving space on the
  shorter side. The source introduction is printed first, at full width.
- [oet.sty](oet.sty) sets the typography and PTXPrint's automatic `s1box`
  cutouts. The 96-point boxes sit on the RV column's right edge, and the
  surrounding text wraps beside them. Additions are gray, sacred names bold,
  untranslated LV words small and struck through. Underscores and
  superscripts remain. Empty verses have a visible `◘` marker.
- [oet.tex](oet.tex) configures a 12.5-point grid, starting 77 points from the
  top. Inside/outside margins are 43/33 points, mirrored for duplex printing;
  the paired-column gap is 16 points. It adds stretch before the native
  combined note box and places the folio in the reserved bottom margin.
  The last note baseline is snapped to the same grid as the body.
  Optional blank versos have no running heads or printed page numbers.
  Page-break penalties keep each cutout and its adjacent lines together so
  a box cannot protrude into the apparatus at a page break.
  Single-version books flush through the normal page builder before the
  end-of-book transition, keeping notes with a final heading that moves pages.
- All footnotes, verse cross-references and heading parallels share one
  numbered apparatus at the bottom of the physical page. Numbers restart for
  each book. A heading's call is printed in its box, with the actual
  insertion attached to its first verse so it reaches the page apparatus.
- XeTeX runs until its placement records settle, up to five passes, then
  `xdvipdfmx` embeds the fonts and creates the PDF. Shell escape is disabled.
  Missing glyphs, misplaced notes, significant line/final-page overflows and
  engine failures stop the build;
  an existing destination PDF is replaced only after success.
- If native pagination moves or duplicates a note, [page_notes.tex](page_notes.tex)
  stores the native note boxes once and the driver allocates measured space on
  each caller's physical page. The reservations grow by whole grid rows until
  placement settles (bounded at 40 passes), keeping full-width notes at the
  page foot. This can leave extra space above the apparatus. The build retains
  the original failure records and a `note-pagination.json` report.
- Long LV joins that overflow a line get last-resort break opportunities at
  their visible join marks. The preprocessor prints `+`, `=` and `÷` word joins
  as underscores. Psalm superscriptions, acrostic labels and speaker
  labels stay in the source text column, outside the inset section headings.
- Collection and multi-book builds use an isolated native PTXPrint run per
  book, with its starting folio supplied before rendering. This prevents
  cutout/diglot state from carrying into the next book. Poppler joins the
  completed PDF pages without scaling or rasterization; page numbers and
  duplex margins remain continuous. A final front-matter pass fills the index.
- The title page reads “Open English Translation of the Bible”. The copyright
  verso and book introductions show the overall draft version from `settings.py`.
  Small lines at each book's end give the RV revision from its ESFM ID and
  the LV set release from the book folder’s `version.json`.

The profile omits source-text illustrations and editorial comments,
and uses one gray treatment for ESFM addition categories, like the SILE
prototype. It preserves source wording and attribution. It is a text proof
for actual-size, long-edge duplex printing; final press imposition and printer
registration remain separate from typesetting.

## Retain inputs and verify

```sh
python3 PTXPrint/typeset.py MRK --build-dir /tmp/oet-mark-build -o mark.pdf
python3 PTXPrint/typeset.py MRK --prepare-only --build-dir /tmp/oet-mark-inputs
python3 -B -m unittest discover -s PTXPrint
```

The retained directory contains generated USFM, TeX, styles, note metadata,
XeTeX logs and native placement records. It is also retained after a failed
build. Collection builds additionally retain a subdirectory for the front
matter and each book, and a `book-pages.tsv` index. `--prepare-only` needs
neither XeTeX nor PTXPrint.

With `pdfplumber` installed, the Mark audit compares extracted text and verse
labels with both sources, checks every matched section, counts all heading
boxes, checks note/caller page associations against native placement records,
and measures margins and the body/note baseline grid:

```sh
python3 PTXPrint/check_pdf.py mark.pdf --build-dir /tmp/oet-mark-build
# Add --version OET-RV or --version OET-LV when auditing those editions.
```

The audit also checks that heading boxes clear the notes. It ignores layout
whitespace and discretionary hyphens when comparing text, and is supplemented
by rendered-page inspection. Native logs can report overfull trial vertical
boxes while searching for legal diglot splits; those are not final page
overflows. The audit's current source
comparison defaults to MRK; pass `--book GEN` for another book. When checking
a retained collection part, supply its printed starting folio with
`--start-page` (from `book-pages.tsv`; subtract one if the part starts with an
inserted blank verso). Some unusual poetry and intro layouts
need additional visual review. `check_publication.py` separately checks the
whole collection's ordering, index targets and complete FRT preface.

Tested with the PTXPrint 3.1.5 source checkout at `f7a9f7bac` and XeTeX
0.999997 / TeX Live 2025. The Ruth proof has 12 B5 pages, compared with
11 in SILE. This implementation
uses native Bible layout machinery plus a small TeX adjustment; the SILE
prototype uses a custom Lua compositor. Neither needs a new Rust component.

Full Mark source/layout audits passed for these proofs:

| Edition | Paper | Pages |
| --- | --- | ---: |
| OET | B5 | 55 |
| OET | A4 | 38 |
| OET | Letter | 40 |
| OET | 160 × 240 mm | 66 |
| OET | 6 × 9 inches | 73 |
| OET-RV | B5 | 32 |
| OET-RV | Letter | 24 |
| OET-LV | B5 | 21 |

Each OET/RV audit includes all 92 heading boxes and 206 notes. The current
Mark LV source has no notes. The delivered B5 parallel proof was also reviewed
as rendered pages, and all its fonts are embedded. Page counts will change
as the translation sources change.
