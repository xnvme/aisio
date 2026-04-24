#!/usr/bin/env python3
import os
import sys
from pathlib import Path
import subprocess
import threading
import time
import importlib.util
import json
from datetime import datetime
from http.server import SimpleHTTPRequestHandler, HTTPServer

import plots

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

PIPX_VENVS_ROOT = os.path.expanduser("~/.local/share/pipx/venvs")
VENV_NAME = "aisio-docs"

LANDING_HOST = "127.0.0.1"
LANDING_PORT = 8000
HTML_HOST = "127.0.0.1"
HTML_PORT = 8001
PDF_HOST = "127.0.0.1"
PDF_PORT = 8002

# watchdog dependencies
try:
    from watchdog.observers import Observer
    from watchdog.events import PatternMatchingEventHandler
except ImportError:
    print("[aisio-docs] Missing dependency: watchdog")
    print("Install it with: pipx inject aisio-docs watchdog")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Global build status (for landing page)
# ---------------------------------------------------------------------------

_build_status_lock = threading.Lock()
_build_status = {
    "last_build_time": None,  # float timestamp
    "last_build_ok": None,  # True / False / None
    "last_build_error": None,  # str or None
    "build_count": 0,
}


def _set_build_status(ok: bool, error: str | None = None) -> None:
    with _build_status_lock:
        _build_status["last_build_time"] = time.time()
        _build_status["last_build_ok"] = ok
        _build_status["last_build_error"] = error
        if ok:
            _build_status["build_count"] += 1


def _get_build_status_snapshot() -> dict:
    with _build_status_lock:
        return dict(_build_status)


def _format_time(ts: float | None) -> str:
    if ts is None:
        return "never"
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def run(cmd: str) -> None:
    print(f"[aisio-docs] {cmd}")
    subprocess.check_call(cmd, shell=True)


def venv_bin_dir() -> str:
    return os.path.join(PIPX_VENVS_ROOT, VENV_NAME, "bin")


def sphinx_build() -> str:
    return os.path.join(venv_bin_dir(), "sphinx-build")


def sphinx_autobuild() -> str:
    return os.path.join(venv_bin_dir(), "sphinx-autobuild")


def find_docs_src() -> str:
    """
    Search upward from the current directory until we find docs/src/conf.py.
    Allows running aisio-docs-* from anywhere inside the project tree.
    """
    cwd = os.getcwd()
    while True:
        candidate = os.path.join(cwd, "docs", "src", "conf.py")
        if os.path.isfile(candidate):
            return os.path.join(cwd, "docs", "src")
        parent = os.path.dirname(cwd)
        if parent == cwd:
            raise RuntimeError("Could not locate docs/src/conf.py")
        cwd = parent


# ---------------------------------------------------------------------------
# Plot generation
# ---------------------------------------------------------------------------


def make_plots(build_dir: str) -> None:
    docs_src = Path(find_docs_src())
    artifacts = docs_src.parent.parent / "artifacts"

    Path(build_dir).mkdir(parents=True, exist_ok=True)

    with plots.artifacts_from_archive(artifacts / "tool-comparison.tar.gz") as archive:
        plots.barplot_tool(archive, build_dir)

    with plots.artifacts_from_archive(artifacts / "pcie-bandwidth-saturation.tar.gz") as archive:
        plots.barplot_sat(archive, build_dir)

    with plots.artifacts_from_archive(artifacts / "cpu-initiated-spdk.tar.gz") as archive:
        plots.lineplot(archive, build_dir, "spdk")
        plots.lineplot(archive, build_dir, "spdk", "qdepth")
        plots.lineplot(archive, build_dir, "spdk", "iosize")
        plots.lineplot(archive, build_dir, "spdk", "ndevs")

    with plots.artifacts_from_archive(artifacts / "cpu-initiated-upcie.tar.gz") as archive:
        plots.lineplot(archive, build_dir, "upcie")

    with plots.artifacts_from_archive(artifacts / "device-initiated-iosize.tar.gz") as archive:
        plots.lineplot(archive, build_dir, "cuda", "iosize")

    with plots.artifacts_from_archive(artifacts / "device-initiated-qdepth.tar.gz") as archive:
        plots.lineplot(archive, build_dir, "cuda", "qdepth")

# ---------------------------------------------------------------------------
# Extract latex_documents from latex_theme.py
# ---------------------------------------------------------------------------


def load_latex_target_pdf(docs_src: str) -> str:
    """
    Read latex_theme.py and extract latex_documents[0][1]
    to determine the correct PDF name.
    """
    theme_path = os.path.join(docs_src, "latex_theme.py")
    if not os.path.isfile(theme_path):
        raise RuntimeError(f"Could not locate latex_theme.py: {theme_path}")

    spec = importlib.util.spec_from_file_location("latex_theme", theme_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    try:
        latex_documents = module.latex_documents
    except AttributeError:
        raise RuntimeError("latex_theme.py does not define latex_documents")

    if not latex_documents:
        raise RuntimeError("latex_documents list is empty")

    # latex_documents = [(master_doc, targetname, title, author, documentclass, ...)]
    target_tex = latex_documents[0][1]  # e.g. "aisio.tex"
    target_pdf = os.path.splitext(target_tex)[0] + ".pdf"
    return target_pdf


# ---------------------------------------------------------------------------
# Build Commands
# ---------------------------------------------------------------------------


def build_html() -> None:
    docs_src = find_docs_src()
    docs_root = os.path.dirname(docs_src)
    html_dir = os.path.join(docs_root, "build", "html")

    make_plots(html_dir)
    run(f"{sphinx_build()} -b html {docs_src} {html_dir}")


def build_pdf() -> None:
    docs_src = find_docs_src()
    docs_root = os.path.dirname(docs_src)
    latex_dir = os.path.join(docs_root, "build", "latex")

    # Mark build as "in progress"
    _set_build_status(ok=False, error="running")

    try:
        make_plots(latex_dir)

        # Run Sphinx -> LaTeX
        run(f"{sphinx_build()} -b latex {docs_src} {latex_dir}")

        # Build the PDF
        run(f"make -C {latex_dir}")

        # Determine correct filename from latex_theme.py
        pdf_basename = load_latex_target_pdf(docs_src)
        pdf_src = os.path.join(latex_dir, pdf_basename)
        pdf_dst = os.path.join(latex_dir, "aisio.pdf")  # normalized output

        if os.path.exists(pdf_src):
            try:
                os.replace(pdf_src, pdf_dst)
            except OSError:
                import shutil

                shutil.copy(pdf_src, pdf_dst)
        else:
            raise RuntimeError(f"Expected PDF not found: {pdf_src}")

        _set_build_status(ok=True, error=None)
        print("[aisio-docs] PDF build complete")

    except Exception as e:
        _set_build_status(ok=False, error=str(e))
        print(f"[aisio-docs] PDF build failed: {e}")
        raise


def clean() -> None:
    docs_src = find_docs_src()
    docs_root = os.path.dirname(docs_src)
    build_dir = os.path.join(docs_root, "build")
    run(f"rm -rf {build_dir}")


# ---------------------------------------------------------------------------
# Recursive Markdown-only watcher using on_modified & on_created
# ---------------------------------------------------------------------------


class MarkdownPDFWatcher(PatternMatchingEventHandler):
    """
    Rebuild PDF ONLY when .md files are created or modified.
    No loops possible because Sphinx never writes .md files.
    """

    def __init__(self, rebuild_fn):
        super().__init__(
            patterns=["*.md"],  # ONLY react to .md files
            ignore_patterns=["*/build/*"],
            ignore_directories=False,
        )
        self.rebuild_fn = rebuild_fn
        self._lock = threading.Lock()
        self._last = 0

    def _trigger(self, event):
        # 0.5s debounce
        now = time.time()
        if now - self._last < 0.5:
            return

        with self._lock:
            self._last = now

            name = os.path.basename(event.src_path)
            print(f"[aisio-docs] {name} updated → rebuilding PDF …")
            try:
                self.rebuild_fn()
            except Exception as e:
                print(f"[aisio-docs] PDF rebuild failed: {e}")

    def on_modified(self, event):
        if not event.is_directory:
            self._trigger(event)

    def on_created(self, event):
        if not event.is_directory:
            self._trigger(event)


def start_pdf_watcher():
    docs_src = find_docs_src()
    handler = MarkdownPDFWatcher(build_pdf)

    observer = Observer()
    observer.schedule(handler, docs_src, recursive=True)
    observer.start()

    print("[aisio-docs] Watching for .md changes …")

    def loop():
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            observer.stop()
        observer.join()

    threading.Thread(target=loop, daemon=True).start()


# ---------------------------------------------------------------------------
# PDF server (port 8002)
# ---------------------------------------------------------------------------


def start_pdf_server():
    docs_src = find_docs_src()
    docs_root = os.path.dirname(docs_src)
    pdf_dir = os.path.join(docs_root, "build", "latex")

    class PDFHandler(SimpleHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/aisio.pdf":
                pdf_file = os.path.join(pdf_dir, "aisio.pdf")

                if not os.path.exists(pdf_file):
                    self.send_response(404)
                    self.end_headers()
                    self.wfile.write(b"No PDF built yet.\n")
                    return

                self.send_response(200)
                self.send_header("Content-type", "application/pdf")
                self.end_headers()
                with open(pdf_file, "rb") as f:
                    self.wfile.write(f.read())
                return

            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not found\n")

    server = HTTPServer((PDF_HOST, PDF_PORT), PDFHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    print(f"[aisio-docs] PDF server at http://{PDF_HOST}:{PDF_PORT}/aisio.pdf")


# ---------------------------------------------------------------------------
# Landing-page server (port 8000) — no PDF iframe, just status + links
# ---------------------------------------------------------------------------


def start_landing_server():
    html_url = f"http://{HTML_HOST}:{HTML_PORT}/"
    pdf_url = f"http://{PDF_HOST}:{PDF_PORT}/aisio.pdf"

    class LandingHandler(SimpleHTTPRequestHandler):
        def do_GET(self):
            if self.path in ("/", "/index.html"):
                status = _get_build_status_snapshot()
                last_time = _format_time(status["last_build_time"])
                ok = status["last_build_ok"]
                error = status["last_build_error"]
                count = status["build_count"]

                if ok is True:
                    badge_text = "OK"
                    badge_class = "badge-ok"
                elif ok is False and error == "running":
                    badge_text = "Building…"
                    badge_class = "badge-running"
                elif ok is False:
                    badge_text = "Error"
                    badge_class = "badge-error"
                else:
                    badge_text = "Unknown"
                    badge_class = "badge-unknown"

                self.send_response(200)
                self.send_header("Content-type", "text/html; charset=utf-8")
                self.end_headers()

                html = f"""
                <!DOCTYPE html>
                <html lang="en">
                <head>
                    <meta charset="utf-8" />
                    <title>AiSIO Docs</title>
                    <style>
                        body {{
                            margin: 0;
                            padding: 0;
                            font-family: system-ui, -apple-system, BlinkMacSystemFont,
                                         "Segoe UI", sans-serif;
                            background: #0b1020;
                            color: #f5f5f7;
                        }}
                        .page {{
                            display: flex;
                            flex-direction: column;
                            min-height: 100vh;
                        }}
                        header {{
                            padding: 1.5rem 2rem;
                            border-bottom: 1px solid rgba(255,255,255,0.06);
                            display: flex;
                            justify-content: space-between;
                            align-items: center;
                        }}
                        header h1 {{
                            margin: 0;
                            font-size: 1.6rem;
                        }}
                        header span.subtitle {{
                            font-size: 0.95rem;
                            color: #a0a4b8;
                        }}
                        main {{
                            flex: 1;
                            display: grid;
                            grid-template-columns: minmax(0, 1.2fr) minmax(0, 1fr);
                            gap: 2rem;
                            padding: 2rem;
                        }}
                        .card {{
                            background: radial-gradient(circle at top left, #1f2937, #020617);
                            border-radius: 1rem;
                            padding: 1.5rem 1.75rem;
                            box-shadow: 0 18px 45px rgba(0,0,0,0.6);
                            border: 1px solid rgba(148,163,184,0.18);
                        }}
                        .card h2 {{
                            margin-top: 0;
                            margin-bottom: 0.4rem;
                            font-size: 1.2rem;
                        }}
                        .card p {{
                            margin-top: 0.2rem;
                            color: #9ca3af;
                            font-size: 0.95rem;
                        }}
                        .button-row {{
                            margin-top: 1rem;
                            display: flex;
                            flex-wrap: wrap;
                            gap: 0.75rem;
                        }}
                        .btn {{
                            display: inline-flex;
                            align-items: center;
                            gap: 0.4rem;
                            border-radius: 999px;
                            padding: 0.6rem 1.2rem;
                            font-size: 0.95rem;
                            font-weight: 500;
                            border: 1px solid transparent;
                            text-decoration: none;
                            color: inherit;
                            cursor: pointer;
                            transition: transform 0.08s ease, box-shadow 0.08s ease, background 0.2s ease, border-color 0.2s ease;
                        }}
                        .btn-primary {{
                            background: linear-gradient(135deg, #2563eb, #38bdf8);
                            box-shadow: 0 10px 25px rgba(37,99,235,0.55);
                        }}
                        .btn-primary:hover {{
                            transform: translateY(-1px);
                            box-shadow: 0 14px 32px rgba(37,99,235,0.7);
                        }}
                        .btn-secondary {{
                            background: rgba(15,23,42,0.9);
                            border-color: rgba(148,163,184,0.4);
                        }}
                        .btn-secondary:hover {{
                            background: rgba(15,23,42,1);
                            transform: translateY(-1px);
                        }}
                        .btn span.icon {{
                            font-size: 1.1rem;
                        }}
                        .meta-grid {{
                            margin-top: 1rem;
                            display: grid;
                            grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
                            gap: 0.75rem;
                            font-size: 0.85rem;
                            color: #9ca3af;
                        }}
                        .meta-item {{
                            display: flex;
                            flex-direction: column;
                            gap: 0.15rem;
                        }}
                        .label {{
                            text-transform: uppercase;
                            letter-spacing: 0.08em;
                            font-size: 0.75rem;
                            color: #6b7280;
                        }}
                        .value {{
                            font-family: "JetBrains Mono", ui-monospace, SFMono-Regular, Menlo,
                                         Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
                            font-size: 0.82rem;
                        }}
                        .badge {{
                            display: inline-flex;
                            align-items: center;
                            justify-content: center;
                            min-width: 80px;
                            padding: 0.25rem 0.7rem;
                            border-radius: 999px;
                            font-size: 0.8rem;
                            font-weight: 600;
                            letter-spacing: 0.05em;
                            text-transform: uppercase;
                        }}
                        .badge-ok {{
                            background: rgba(22, 163, 74, 0.16);
                            color: #4ade80;
                            border: 1px solid rgba(22, 163, 74, 0.5);
                        }}
                        .badge-running {{
                            background: rgba(59, 130, 246, 0.14);
                            color: #93c5fd;
                            border: 1px solid rgba(59, 130, 246, 0.5);
                        }}
                        .badge-error {{
                            background: rgba(239, 68, 68, 0.16);
                            color: #fca5a5;
                            border: 1px solid rgba(239, 68, 68, 0.55);
                        }}
                        .badge-unknown {{
                            background: rgba(148, 163, 184, 0.16);
                            color: #e5e7eb;
                            border: 1px solid rgba(148, 163, 184, 0.55);
                        }}
                        .badge-dot {{
                            display: inline-block;
                            width: 0.45rem;
                            height: 0.45rem;
                            border-radius: 999px;
                            margin-right: 0.3rem;
                            background: currentColor;
                        }}
                        footer {{
                            padding: 0.75rem 2rem 1.3rem;
                            font-size: 0.75rem;
                            color: #6b7280;
                            display: flex;
                            justify-content: space-between;
                        }}
                        @media (max-width: 960px) {{
                            main {{
                                grid-template-columns: minmax(0, 1fr);
                            }}
                        }}
                    </style>
                </head>
                <body>
                    <div class="page">
                        <header>
                            <div>
                                <h1>AiSIO Documentation</h1>
                                <span class="subtitle">
                                    Accelerator-integrated Storage I/O • Whitepaper &amp; System Docs
                                </span>
                            </div>
                            <div>
                                <span id="status-badge" class="badge {badge_class}">
                                    <span class="badge-dot"></span>
                                    <span id="status-text">{badge_text}</span>
                                </span>
                            </div>
                        </header>
                        <main>
                            <section class="card">
                                <h2>Developer View</h2>
                                <p>
                                    Use the HTML docs while iterating on content, and rely on the
                                    PDF for final layout, review, and sharing.
                                </p>
                                <div class="button-row">
                                    <a class="btn btn-primary" href="{html_url}" target="_blank" rel="noopener noreferrer">
                                        <span class="icon">📘</span>
                                        <span>Open HTML Docs</span>
                                    </a>
                                    <a class="btn btn-secondary" href="{pdf_url}" target="_blank" rel="noopener noreferrer">
                                        <span class="icon">📄</span>
                                        <span>Open PDF in new tab</span>
                                    </a>
                                </div>
                                <div class="meta-grid">
                                    <div class="meta-item">
                                        <span class="label">Last PDF build</span>
                                        <span class="value" id="status-last-build">{last_time}</span>
                                    </div>
                                    <div class="meta-item">
                                        <span class="label">Successful builds</span>
                                        <span class="value" id="status-build-count">{count}</span>
                                    </div>
                                    <div class="meta-item">
                                        <span class="label">Build message</span>
                                        <span class="value" id="status-error">{error or "—"}</span>
                                    </div>
                                </div>
                            </section>
                            <section class="card">
                                <h2>Build Status</h2>
                                <p>
                                    Status is updated automatically as you edit <code>.md</code> files
                                    under <code>docs/src</code>. Use this to confirm that PDF generation
                                    is healthy while you write.
                                </p>
                                <div class="meta-grid">
                                    <div class="meta-item">
                                        <span class="label">State</span>
                                        <span class="value" id="status-state-text">{badge_text}</span>
                                    </div>
                                    <div class="meta-item">
                                        <span class="label">Last updated</span>
                                        <span class="value" id="status-last-build-2">{last_time}</span>
                                    </div>
                                </div>
                            </section>
                        </main>
                        <footer>
                            <span>AiSIO Docs helper • Serving on 127.0.0.1:{LANDING_PORT}</span>
                            <span>HTML: :{HTML_PORT} • PDF: :{PDF_PORT}</span>
                        </footer>
                    </div>
                    <script>
                        const STATUS_ENDPOINT = "/status";
                        const STATUS_BADGE = document.getElementById("status-badge");
                        const STATUS_TEXT = document.getElementById("status-text");
                        const STATUS_LAST_BUILD = document.getElementById("status-last-build");
                        const STATUS_LAST_BUILD_2 = document.getElementById("status-last-build-2");
                        const STATUS_BUILD_COUNT = document.getElementById("status-build-count");
                        const STATUS_ERROR = document.getElementById("status-error");
                        const STATUS_STATE_TEXT = document.getElementById("status-state-text");

                        function setBadge(state) {{
                            STATUS_BADGE.classList.remove(
                                "badge-ok", "badge-running", "badge-error", "badge-unknown"
                            );
                            STATUS_BADGE.classList.add("badge-" + state.className);
                            STATUS_TEXT.textContent = state.label;
                            STATUS_STATE_TEXT.textContent = state.label;
                        }}

                        async function pollStatus() {{
                            try {{
                                const res = await fetch(STATUS_ENDPOINT, {{ cache: "no-store" }});
                                if (!res.ok) return;
                                const data = await res.json();

                                STATUS_LAST_BUILD.textContent = data.last_build_time_human || "never";
                                STATUS_LAST_BUILD_2.textContent = data.last_build_time_human || "never";
                                STATUS_BUILD_COUNT.textContent = data.build_count ?? 0;
                                STATUS_ERROR.textContent = data.last_build_error || "—";

                                let badgeState = {{ className: "unknown", label: "Unknown" }};
                                if (data.last_build_ok === true) {{
                                    badgeState = {{ className: "ok", label: "OK" }};
                                }} else if (data.last_build_ok === false && data.last_build_error === "running") {{
                                    badgeState = {{ className: "running", label: "Building…" }};
                                }} else if (data.last_build_ok === false) {{
                                    badgeState = {{ className: "error", label: "Error" }};
                                }}
                                setBadge(badgeState);
                            }} catch (e) {{
                                // ignore polling errors
                            }}
                        }}

                        // Poll every 10 seconds
                        setInterval(pollStatus, 10000);
                        // Initial poll
                        pollStatus();
                    </script>
                </body>
                </html>
                """
                self.wfile.write(html.encode("utf-8"))
                return

            if self.path == "/status":
                status = _get_build_status_snapshot()
                payload = {
                    "last_build_time": status["last_build_time"],
                    "last_build_time_human": _format_time(status["last_build_time"]),
                    "last_build_ok": status["last_build_ok"],
                    "last_build_error": status["last_build_error"],
                    "build_count": status["build_count"],
                }
                body = json.dumps(payload).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not found\n")

    server = HTTPServer((LANDING_HOST, LANDING_PORT), LandingHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    print(f"[aisio-docs] Landing page at http://{LANDING_HOST}:{LANDING_PORT}/")


# ---------------------------------------------------------------------------
# Serve command
# ---------------------------------------------------------------------------


def serve() -> None:
    docs_src = find_docs_src()
    docs_root = os.path.dirname(docs_src)
    html_dir = os.path.join(docs_root, "build", "html")

    # Watch for .md changes -> rebuild PDF
    start_pdf_watcher()

    # Start PDF server on 8002
    start_pdf_server()

    # Start landing page on 8000
    start_landing_server()

    make_plots(html_dir)

    # Live HTML server on 8001
    cmd = (
        f"{sphinx_autobuild()} "
        f"{docs_src} {html_dir} "
        f"--host {HTML_HOST} --port {HTML_PORT} "
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
        print(
            f"[aisio-docs] command failed with exit code {e.returncode}",
            file=sys.stderr,
        )
        return e.returncode

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
