# SILE


Here we will have code to use [SILE](https://sile-typesetter.org/) to typeset a USX Bible in one or two columns.



## Installation

### Quick procedure

If you have Docker installed, you can use a file to build an image containing SILE, Luarocks, the _re·sil·ient_ collection of classes and packages, other tools used by some of the modules, and a curated set of good fonts.

Go to the [Awesome SILE books](https://github.com/Omikhleia/awesome-sile-books#or-with-a-ready-to-go-docker-image) and follow the instructions for building and using a custom docker image.

### Manual procedure

You are on your own checking that you have the right versions of the dependencies and a proper working installation:

- [SILE](https://github.com/sile-typesetter/sile) 0.14.**11** or upper

  See installation instructions on the SILE website.

- [LuaRocks](https://luarocks.org/)

  See installation instructions on the LuaRocks website.

- The _re·sil·ient_ collection of classes & packages for SILE, a.k.a. [resilient.sile](https://github.com/Omikhleia/resilient.sile).

  ```bash
  luarocks install resilient.sile
  ```

  Be sure to upgrade to the latest version.

- Decent choice of fonts: Libertinus.

### Usage

For any bible in the repository, you can generate a PDF with a one-line command, run from the base folder of this repository (so one level above this very README file).

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

 - unfoldingWord Literal Text (ULT)

   ```bash
   sile -u inputters.silm SILE/ULT/ult.silm
   ```
