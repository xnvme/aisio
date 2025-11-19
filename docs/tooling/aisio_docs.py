import os
import sys
import subprocess

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Adjust this if your pipx venv root is different:
PIPX_VENVS_ROOT = os.path.expanduser("~/.local/share/pipx/venvs")
VENV_NAME = "aisio-docs"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def run(cmd: str) -> None:
    """Run a shell command and echo it."""
    print(f"[aisio-docs] {cmd}")
    subprocess.check_call(cmd, shell=True)


def venv_bin_dir() -> str:
    """Return the bin/ directory of the aisio-docs pipx venv."""
    return os.path.join(PIPX_VENVS_ROOT, VENV_NAME, "bin")


def sphinx_build() -> str:
    """Return the absolute path to sphinx-build inside the aisio-docs venv."""
    return os.path.join(venv_bin_dir(), "sphinx-build")


def sphinx_autobuild() -> str:
    """Return the absolute path to sphinx-autobuild inside the aisio-docs venv."""
    return os.path.join(venv_bin_dir(), "sphinx-autobuild")


def find_docs_src() -> str:
    """
    Search upward from the current directory until we find docs/src/conf.py.

    This lets you run aisio-docs-* from anywhere inside the project tree.
    """
    cwd = os.getcwd()

    while True:
        candidate = os.path.join(cwd, "docs", "src", "conf.py")
        if os.path.isfile(candidate):
            return os.path.join(cwd, "docs", "src")

        parent = os.path.dirname(cwd)
        if parent == cwd:  # reached filesystem root
            raise RuntimeError(
                "Could not locate docs/src/conf.py relative to current directory."
            )

        cwd = parent


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def build_html() -> None:
    docs_src = find_docs_src()
    docs_root = os.path.dirname(docs_src)
    html_dir = os.path.join(docs_root, "build", "html")

    run(f"{sphinx_build()} -b html {docs_src} {html_dir}")


def build_pdf() -> None:
    docs_src = find_docs_src()
    docs_root = os.path.dirname(docs_src)
    latex_dir = os.path.join(docs_root, "build", "latex")

    # First: generate LaTeX sources
    run(f"{sphinx_build()} -b latex {docs_src} {latex_dir}")
    # Then: compile to PDF using the generated Makefile
    run(f"make -C {latex_dir}")


def clean() -> None:
    docs_src = find_docs_src()
    docs_root = os.path.dirname(docs_src)
    build_dir = os.path.join(docs_root, "build")

    run(f"rm -rf {build_dir}")


def serve() -> None:
    docs_src = find_docs_src()
    docs_root = os.path.dirname(docs_src)
    html_dir = os.path.join(docs_root, "build", "html")

    cmd = (
        f"{sphinx_autobuild()} "
        f"{docs_src} {html_dir} "
        f"--host 127.0.0.1 --port 8000 "
        f'--watch "{docs_src}"'
    )

    run(cmd)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("Usage: aisio-docs <html|pdf|clean|serve>")
        return 1

    cmd = argv[1]

    try:
        if cmd == "html":
            build_html()
        elif cmd == "pdf":
            build_pdf()
        elif cmd == "clean":
            clean()
        elif cmd == "serve":
            serve()
        else:
            print("Unknown command:", cmd)
            print("Usage: aisio-docs <html|pdf|clean|serve>")
            return 1
    except RuntimeError as e:
        print(f"[aisio-docs] ERROR: {e}", file=sys.stderr)
        return 1
    except subprocess.CalledProcessError as e:
        # Bubble up the underlying tool failure but with a bit of context
        print(
            f"[aisio-docs] command failed with exit code {e.returncode}",
            file=sys.stderr,
        )
        return e.returncode

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
