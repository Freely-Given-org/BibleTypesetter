# Printing the Open English Translation with SILE

[Open the B5 Ruth print proof](OET-RUT.B5.print.pdf) or [screen proof](OET-RUT.B5.screen.pdf). Page 2 shows the matched columns, inset headings and a page-bottom note. Page 10 gives the RV book revision and the LV OT set release.

## Build a book

For all print/screen collections and all individual books, use
`python3 SILE/build_pdfs.py`. See [the download batch documentation](../README.md#building-the-complete-sile-download-catalogue)
for automatic OET makefile integration, OBD hosting, catalogues, and incremental rebuilds.

[settings.toml](settings.toml) extends [the shared OET profile](../profiles/oet.toml)
and sets page numbers to `"outside"` by default. It supplies the publication's
sources, wording, licence, colours and linked logos. Use `--config PATH` for
another publication profile (`--layout-settings` remains an alias).
Set `page_numbers = "centred"` to centre folios.
See [publication profiles and logo settings](../README.md#publication-profiles).

Use Python 3.11 or newer, SILE 0.15 with its HarfBuzz and libtexpdf backend, and the **Gentium Plus**, **Lato**, **DejaVu Sans** and **Ezra SIL** fonts. Ezra SIL preserves Hebrew in translator notes. The proof was built with SILE 0.15.12. OT/Acts pairing additionally uses BibleOrgSys's verse mappings.

From the BibleTypesetter repository root, with the OET repository checked out alongside it, run

```sh
python3 SILE/typeset.py RUT -o SILE/OET-RUT.B5.print.pdf
```

MRK is the default. To print a selection into one PDF, pass OET filename codes in reading order. For example

```sh
python3 SILE/typeset.py JN2 PHM --oet-root /path/to/OpenEnglishTranslation--OET -o letters.pdf
```

For a complete collection, use `OT`, `DC`, `NT` or `ALL` and
`--book-order oet|traditional`. These modes add a title page, copyright/licence
verso, contents index, and the RV preface from FRT. Contents and preface start
on right-hand pages. Add `--start-books-on-odd-pages` for right-hand starts for
every book too (off by default). See [collection options and dependencies](../README.md#collections-and-book-order)
for DC chapter pairing, missing versions, source aliases and verse mappings.

```sh
python3 SILE/typeset.py NT --book-order oet --build-dir /tmp/sile-nt -o OET-NT.pdf
python3 SILE/typeset.py ALL --book-order traditional --version OET-LV --paper-size A4
python3 SILE/typeset.py DC --prepare-only --build-dir /tmp/sile-dc-inputs
```

Use `--sile /path/to/bin/sile` or set `SILE_BIN` to choose a built executable. The driver otherwise uses `sile` on PATH, then a unique locally cached Nix SILE build if available. For installation options, see the [SILE project](https://github.com/sile-typesetter/sile#readme).

## Print or screen

Use `--print` (default) for greyscale with full visible URLs, or `--screen`
for coloured headings, verse numbers and links with shortened URL labels.
Both have live web links, including the reading link after the toolchain credit.
For example, `python3 SILE/typeset.py RUT --screen` creates
`OET-RUT.B5.screen.pdf`. These are CLI flags, not TOML settings.
See [shared output options](../README.md#print-or-screen).

## Paper size and edition

`--paper-size` accepts `B5` (the default), `A4`, `Letter` (8.5 × 11 inches), or a custom width × height in millimetres or inches. For example

```sh
python3 SILE/typeset.py MRK --paper-size A4 -o mark-a4.pdf
python3 SILE/typeset.py MRK --paper-size Letter -o mark-letter.pdf
python3 SILE/typeset.py MRK --paper-size "160x240mm" -o mark-custom.pdf
python3 SILE/typeset.py MRK --paper-size "6 x 9 inches" -o mark-six-by-nine.pdf
```

Units may follow both dimensions, as in `"210mm x 297mm"`, or the final dimension alone. Width comes first, so `"297x210mm"` produces landscape A4. Type sizes, margins and the baseline grid stay fixed while line widths and the number of rows per page adjust to the paper. Dimensions must leave sufficient space for the text, headings and notes.

In the supplied profile, `--version` selects `OET` (both versions side by side, the default), `OET-RV`, or `OET-LV`. Each single-version edition uses its own source text, title and full-width introduction. RV-only scripture flows down the left column, then the right; its end credits span the page. `editions.OET-RV.body_columns = 2` selects this layout. LV-only scripture remains full width. RV-only output retains its boxed section headings. LV-only output follows the LV’s own paragraphs and chapters.

```sh
python3 SILE/typeset.py MRK --version OET-RV --paper-size A4
python3 SILE/typeset.py MRK --version OET-LV --paper-size "8.5x11in"
```

The default output names for these single-version examples are `OET-RV-MRK.A4.print.pdf` and `OET-LV-MRK.8.5x11in.print.pdf`. Other paper labels include `.B5.print.pdf`, `.Letter.print.pdf`, and `.160x240mm.print.pdf`; a collection is named, for example, `OET-NT-oet.B5.print.pdf`. An explicit `-o` filename is used exactly as supplied. Names of versions and paper presets are case-insensitive. Only the selected version’s source files are needed for single-version builds.

## Print layout

- **Page and register.** The supplied proof uses ISO B5 (176 × 250 mm), actual size, duplex, long-edge binding. The inside margin is 43 pt, the outside margin 33 pt, and the parallel column gap 16 pt. They mirror across the sheet. RV text and page notes share a 12.5 pt baseline grid. In the parallel edition, LV uses 9.4 pt type on 11.25 pt leading; RV uses 10.4 pt type. RV occupies 53% of the available column width on the outside of each page, with LV in the narrower inside column. Matched sections start level, so LV grid registration is approximate. The first body baseline is 77 pt from the top, and the last row is calculated from the selected paper height. Printer registration and show-through can be judged by holding a printed sheet to the light.
- **Matched sections.** Each RV heading starts a paired block at its verse address. The two versions flow independently until the next block, including across page turns. The shorter side can leave white space. Paragraphs and poetry continuations stay with their verse. Verse bridges such as Mark 7:21–22 align with both individual LV verses.
- **Headings and apparatus.** A heading box occupies the right edge of the RV column only for the lines it needs. Boxes stay on one page. Footnotes (\f), verse cross-references (\x), and parallel passages attached to headings (\r) have numbered calls. The compositor measures notes from both columns before choosing each physical page break and sets them at the foot of that page.
- **Translation typography.** Lighter ink marks additions, bold marks sacred names, and a small struck word represents untranslated LV material. LV `+`, `=` and `÷` joins become underscores; a broken underscore is repeated at the start of the next line. RV uses standard English hyphenation. Superscripts are retained. Mark’s RV longer ending keeps the source’s lighter styling. An empty LV section has an explicit range and absence label. The introduction carries the attribution and licence.
- **Publication details.** The title page reads “Open English Translation of the Bible”. The copyright verso and book introductions carry the overall draft version from `settings.py`. The book-end lines give the RV revision from its ESFM ID and the LV set release from the book folder’s `version.json`.

## Implementation and scope

[The Python driver](typeset.py) reads the selected files from `translatedTexts/ReadersVersion/OET-RV_*.ESFM` and `derivedTexts/auto_edited_*_ESFM/OET-LV_*.ESFM`. It removes word-table IDs and editorial control codes, retains printable text and notes, validates matching verse coverage for paired output, and passes structured XML to SILE. It replaces the requested PDF only after a successful render.

[The SILE document class](classes/oet.lua) shapes and measures the actual glyphs with SILE, wraps the columns and boxes, fits the notes, and draws embedded text and vector rules. Page dimensions and typography are defined at the top of the class. SILE’s existing Rust executable runs the Lua class.

The driver accepts all current OT, DC and NT sources. It reports unsupported markers or unresolved alignment with a source location where available. Collection builds isolate each book's SILE process and join its pages without rescaling. The print profile omits source-text illustrations and editorial comments, and uses one grayscale treatment for the ESFM addition categories.

Run the paper-size and edition-selection regression checks with `python3 -B -m unittest discover -s SILE`.
