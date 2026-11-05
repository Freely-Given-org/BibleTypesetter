# Printing the Open English Translation with SILE

[Open the B5 Ruth proof](OET-RUT.B5.pdf). Page 2 shows the matched columns, inset headings and a page-bottom note. Page 11 gives the RV book revision and the LV OT set release.

## Build a book

Use Python 3.11 or newer, SILE 0.15 with its HarfBuzz and libtexpdf backend, and the **Gentium Plus**, **Lato**, **DejaVu Sans** and **Ezra SIL** fonts. Ezra SIL preserves Hebrew in translator notes. The proof was built with SILE 0.15.12. OT/Acts pairing additionally uses BibleOrgSys's verse mappings.

From the BibleTypesetter repository root, with the OET repository checked out alongside it, run

```sh
python3 SILE/typeset.py RUT -o SILE/OET-RUT.B5.pdf
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

## Paper size and edition

`--paper-size` accepts `B5` (the default), `A4`, `Letter` (8.5 × 11 inches), or a custom width × height in millimetres or inches. For example

```sh
python3 SILE/typeset.py MRK --paper-size A4 -o mark-a4.pdf
python3 SILE/typeset.py MRK --paper-size Letter -o mark-letter.pdf
python3 SILE/typeset.py MRK --paper-size "160x240mm" -o mark-custom.pdf
python3 SILE/typeset.py MRK --paper-size "6 x 9 inches" -o mark-six-by-nine.pdf
```

Units may follow both dimensions, as in `"210mm x 297mm"`, or the final dimension alone. Width comes first, so `"297x210mm"` produces landscape A4. Type sizes, margins and the baseline grid stay fixed while line widths and the number of rows per page adjust to the paper. Dimensions must leave sufficient space for the text, headings and notes.

`--version` selects `OET` (both versions side by side, the default), `OET-RV`, or `OET-LV`. Each single-version edition uses one full-width column and its own source text, title and introduction. RV-only output retains its boxed section headings. LV-only output follows the LV’s own paragraphs and chapters.

```sh
python3 SILE/typeset.py MRK --version OET-RV --paper-size A4
python3 SILE/typeset.py MRK --version OET-LV --paper-size "8.5x11in"
```

The default output names for these single-version examples are `OET-RV-MRK.A4.pdf` and `OET-LV-MRK.8.5x11in.pdf`. Other paper labels include `.B5.pdf`, `.Letter.pdf`, and `.160x240mm.pdf`; a collection is named, for example, `OET-NT-oet.B5.pdf`. An explicit `-o` filename is used exactly as supplied. Names of versions and paper presets are case-insensitive. Only the selected version’s source files are needed for single-version builds.

## Print layout

- **Page and register.** The supplied proof uses ISO B5 (176 × 250 mm), actual size, duplex, long-edge binding. The inside margin is 43 pt, the outside margin 33 pt, and the parallel column gap 16 pt. They mirror across the sheet. Text and page notes share a 12.5 pt baseline grid. The first body baseline is 77 pt from the top, and the last row is calculated from the selected paper height. Printer registration and show-through can be judged by holding a printed sheet to the light.
- **Matched sections.** Each RV heading starts a paired block at its verse address. The two versions flow independently until the next block, including across page turns. The shorter side can leave white space. Paragraphs and poetry continuations stay with their verse. Verse bridges such as Mark 7:21–22 align with both individual LV verses.
- **Headings and apparatus.** A heading box occupies the right edge of the RV column only for the lines it needs. Boxes stay on one page. Footnotes (\f), verse cross-references (\x), and parallel passages attached to headings (\r) have numbered calls. The compositor measures notes from both columns before choosing each physical page break and sets them at the foot of that page.
- **Translation typography.** Lighter ink marks additions, bold marks sacred names, and a small struck word represents untranslated LV material. LV underscores and superscripts are retained. Mark’s RV longer ending keeps the source’s lighter styling. An empty LV section has an explicit range and absence label. The introduction carries the attribution and licence.
- **Publication details.** The title page reads “Open English Translation of the Bible”. The copyright verso and book introductions carry the overall draft version from `settings.py`. The book-end lines give the RV revision from its ESFM ID and the LV set release from the book folder’s `version.json`.

## Implementation and scope

[The Python driver](typeset.py) reads the selected files from `translatedTexts/ReadersVersion/OET-RV_*.ESFM` and `derivedTexts/auto_edited_*_ESFM/OET-LV_*.ESFM`. It removes word-table IDs and editorial control codes, retains printable text and notes, validates matching verse coverage for paired output, and passes structured XML to SILE. It replaces the requested PDF only after a successful render.

[The SILE document class](classes/oet.lua) shapes and measures the actual glyphs with SILE, wraps the columns and boxes, fits the notes, and draws embedded text and vector rules. Page dimensions and typography are defined at the top of the class. SILE’s existing Rust executable runs the Lua class.

The driver accepts all current OT, DC and NT sources. It reports unsupported markers or unresolved alignment with a source location where available. Collection builds isolate each book's SILE process and join its pages without rescaling. The print profile omits illustrations, web link destinations, and editorial comments, and uses one grayscale treatment for the ESFM addition categories.

Run the paper-size and edition-selection regression checks with `python3 -B -m unittest discover -s SILE`.


# Resilient

This folder contains master files for the various USX bibles in this repository, to typeset them with the [SILE](https://sile-typesetter.org/) typesetting system and the _re·sil·ient_ collection of classes and packages.

## Installation

### Quick procedure

If you have Docker installed, you can use a file to build an image containing SILE, Luarocks, the _re·sil·ient_ collection of classes and packages, other tools used by some of the modules, and a curated set of good fonts.

Go to the [Awesome SILE books](https://github.com/Omikhleia/awesome-sile-books#or-with-a-ready-to-go-docker-image) and follow the instructions for building and using a custom docker image.

### Manual procedure

You are on your own checking that you have the right versions of the dependencies and a proper working installation:

- [SILE](https://github.com/sile-typesetter/sile)

  See installation instructions on the SILE website, and be sure to install the latest version.

- [LuaRocks](https://luarocks.org/)

  See installation instructions on the LuaRocks website.

- The _re·sil·ient_ collection of classes & packages for SILE, a.k.a. [resilient.sile](https://github.com/Omikhleia/resilient.sile).

  ```bash
  luarocks install resilient.sile
  ```

  Be sure to upgrade to the latest version.

- Decent choice of fonts: Libertinus.

### Usage

For any bible in the repository, you can generate a PDF with a one-line command, run from the base folder of this repository (so one level _above_ this very README file).

 - English bibles
    - The King James Version of the Holy Bible (KJB)

      ```bash
      sile -u inputters.silm SILE/KJB/kjb.silm
      ```

    - Berean Study Bible (BSB)

      ```bash
      sile -u inputters.silm SILE/BSB/bsb.silm
      ```

    - World English Bible (WEB)

      ```bash
      sile -u inputters.silm SILE/WEB/web.silm
      ```

    - unfoldingWord® Literal Text (ULT)

      ```bash
      sile -u inputters.silm SILE/ULT/ult.silm
      ```

 - French bibles
    - FOB (Français courant, version œcuménique de la Bible)

      ```bash
      sile -u inputters.silm SILE/FOB/fob.silm
      ```
 
    - NCL (Nouvelle Bible Segond)

      ```bash
      sile -u inputters.silm SILE/NCL/ncl.silm
      ```

    - SBL (Sainte Bible libre pour le monde)

      ```bash
      sile -u inputters.silm SILE/SBL/sbl.silm
      ```

 - Greek bible
    - UGNT (unfoldingWord® Greek New Testament)

      ```bash
      sile -u inputters.silm SILE/UGNT/ugnt.silm
      ```
    
    - TCGNT (Text-Critical Greek New Testament)

      ```bash
      sile -u inputters.silm SILE/TCGNT/tcgnt.silm
      ```
