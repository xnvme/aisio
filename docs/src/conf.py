import os
import sys
from datetime import datetime


project = "AiSIO"
author = "Simon A. F. Lund"
year = datetime.now().year
release = "0.1"

extensions = [
    "myst_parser",
    "sphinx_book_theme",
    "sphinxcontrib.bibtex",
    #    "sphinx_external_toc",
]


bibtex_bibfiles = ["references.bib"]
bibtex_default_style = "unsrt"
bibtex_header_str = " "

myst_enable_extensions = [
    "colon_fence",
    "deflist",
    "linkify",
    "substitution",
    "tasklist",
]

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

html_theme = "sphinx_book_theme"
html_static_path = ["_static"]

html_theme_options = {
    "repository_url": "https://github.com/xnvme/aisio",
    "use_repository_button": True,
    "use_issues_button": True,
    "use_download_button": True,
    "navigation_with_keys": True,
    "path_to_docs": "docs/src",
    "logo": {
        # If you want, later: "image_light": "aisio-logo.svg"
    },
    "show_navbar_depth": 3,
    "max_navbar_depth": 3,
}

# external_toc_path = "_toc.yml"
# external_toc_exclude_missing = False

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from latex_theme import latex_engine, latex_documents, latex_elements
