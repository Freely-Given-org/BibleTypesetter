# BibleTypesetter

Using [SILE typesetter](https://sile-typesetter.org/) to create elegant Bible PDFs

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
