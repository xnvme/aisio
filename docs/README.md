# Compiling the Documentation

To compile the documentation you need the following tools and packages on your
systems:

* Python3

* pipx

  - Ensure pipx-installed tools are available in PATH
  - Run ``pipx ensurepath`` and reload your SHELL

* make

* texlive, texlive-full, texlive-extra, or latexmk on macOS

* git-lfs

The benchmark archives under ``artifacts/`` are stored with Git LFS and are
required by the plot-generation step that runs before Sphinx. After cloning,
fetch them with:

```bash
git lfs pull
```

Without this, ``artifacts/*.tar.gz`` remain pointer stubs and the build fails
in plot generation with a "not in gzip format" error.

With the above in place do, from within ``aisio/docs`` run:

```bash
pipx install ./tooling
```

Afterwhich you can run:

```bash
aisio-docs-serve
```

Then whenever the documentation sources ``aisio/docs/src/`` change, then the
**HTML** and **PDF** version of the docs are rebuilt. point your browser to:
https://localhost:8000

It has a status page of the build-process along with links to **HTML** and
**PDF**. To explicitly build only **HTML** or **PDF** then run:

```bash
# Build HTML
aisio-docs-build-html

# Build PDF
aisio-docs-build-pdf
```
