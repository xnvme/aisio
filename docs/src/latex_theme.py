# AISIO Whitepaper LaTeX Theme (Single-Column, Clean, Book-Quality)

latex_engine = "lualatex"

latex_documents = [
    (
        "index",
        "aisio.tex",
        "AiSIO Whitepaper",
        "Simon A. F. Lund, Karl Bonde Torp, Nadja Brix Koch, Javier González",
        "report",  # stable long-form layout
        False,
    ),
]

latex_elements = {
    "papersize": "a4paper",
    "pointsize": "11pt",
    "classoptions": "oneside,openany",
    "sphinxsetup": """
        hmargin=2.4cm,
        vmargin=2.6cm,
        VerbatimColor={rgb}{0.97,0.97,0.97},
        VerbatimBorderColor={rgb}{0.85,0.85,0.85},
    """,
    "fontpkg": r"""
\usepackage{libertinus}
\usepackage[scaled=0.92]{inconsolata}
""",
    "preamble": r"""
\usepackage{microtype}
\usepackage{xcolor}
\usepackage{titlesec}
\usepackage{fancyhdr}
\usepackage{lastpage}
\usepackage{setspace}

% AISIO colors
\definecolor{AisioBlue}{HTML}{0052CC}
\definecolor{AisioGrey}{HTML}{3A3A3A}

% ----- Section Styling -----
\titleformat{\chapter}[display]
  {\normalfont\bfseries\Huge\color{AisioBlue}}
  {\Large\color{AisioGrey}\chaptertitlename~\thechapter}
  {1ex}
  {\vspace{1ex}}
  [\vspace{0.5ex}\titlerule]

\titleformat{\section}
  {\normalfont\Large\bfseries\color{AisioBlue}}
  {\thesection}{0.75em}{}

\titleformat{\subsection}
  {\normalfont\large\bfseries\color{AisioGrey}}
  {\thesubsection}{0.75em}{}

% Paragraph and line spacing
\setlength{\parskip}{0.75em}
\setlength{\parindent}{0pt}
\onehalfspacing

% Header and footer
\pagestyle{fancy}
\fancyhf{}
\fancyhead[L]{\textcolor{AisioGrey}{AiSIO Whitepaper}}
\fancyhead[R]{\textcolor{AisioGrey}{\nouppercase{\leftmark}}}
\fancyfoot[C]{\thepage\ / \pageref{LastPage}}
\renewcommand{\headrulewidth}{0pt}

""",
    "maketitle": r"""
\begin{titlepage}
  \centering
  \vspace*{3cm}
  {\Huge\bfseries\color{AisioBlue} AiSIO\par}
  \vspace{0.6cm}
  {\Large Accelerator-integrated Storage I/O\par}

  \vspace{1.5cm}
  {\large\color{AisioGrey}
    Whitepaper • System Architecture • Open Research \par
  }

  \vspace{2.5cm}
  {\normalsize
    Simon A. F. Lund \\
    Karl Bonde Torp \\
    Nadja Brix Koch \\
    Javier González \\[0.4em]
    \textit{Samsung Semiconductor}
  }

  \vfill

  {\large
    Version {{ release }} \\
    \today
  }

  \vspace*{2cm}
\end{titlepage}
\clearpage
""",
}
