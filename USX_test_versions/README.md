# USX Test Versions folder

In this folder we provide USX XML Bible files converted from USFM to USX by Paratext 9
in order to be sure that the test Bibles are in the best official form of USX.

(Our own [BibleOrgSys](https://github.com/Freely-Given-org/BibleOrgSys) can also
convert USFM to USX, but we didn't want the SILE programmers to be distracted
by any possible defects or differences in the XML produced by BibleOrgSys.

## Copyright issues

Of course, we can't reformat or publish copyrighted Bibles here.
We are very grateful to [eBible.org](https://ebible.org/)
for providing access to [open-licenced USFM Bibles](https://ebible.org/Scriptures/)
(that we then converted to USX with the now unsupported
[Paratext 9.0.100.10238](https://paratext.org/download/download-paratext-for-linux/) running on Ubuntu Linux).

## Metadata

Unfortunately, the raw Bible book USX files contain very little metadata (beyond the "book" titles, etc.)
Obviously to typeset a Bible, we need "work" metadata including the work title, the copyright, the licence, etc.
Some of this may be in a FRT (preface) or INT file if they exist (see [here](https://ubsicap.github.io/usx/peripherals.html)),
but many versions don't supply this information (especially older works).

(We expect that for new and current works, in the future they might be packaged
in [Scripture Burritos](https://docs.burrito.bible/en/v1.0.0-rc1/) which will help considerably.)

So meanwhile, we may need to define and create some metadata files in order to typeset the title pages, etc.???

## Updates

For those translation projects that are still in process,
we will attempt to update the USX copies from time to time.

Note that Paratext does include many open-licensed Bibles as resources,
but sadly it doesn't enable exports for anything it considers as a "resource"
(even if they are open-licensed).

This means that the process works like this:
1. Download open-licensed Bible files from eBible.org or other sources
2. Optional: Copy only the USFM files into another temporary folder (thus removing any non-USFM files)
2. Create a new USFM3 project in Paratext -- set Language, Type of Project, and select All Books, then Ok, then USFM3
3. (The above creates a folder in your Paratext8Projects folder containing the following files: Settings.xml, ProjectProgress.xml, <lg>.ldml, CommentTags.xml, and unique.id)
3. In the project window, use **Manage books** / **Import book(s)…** to select and import only the USFM files
Note: Fortunately Paratext uses the \id lines containing the
[book id](https://ubsicap.github.io/usfm/identification/books.html),
and not the filenames, because eBible.org uses a custom book numbering scheme.
5. In the project window, use **Advanced** / **Export project to USX…** to create the desired folder and export the USX files
2. Use Paratext to import the USFM files into a Paratext project
3. Use Paratext to export the project files as USX.
