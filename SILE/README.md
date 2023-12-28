# SILE

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
