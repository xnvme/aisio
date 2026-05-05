from __future__ import annotations

import json
import os
import shutil
import sys
from argparse import Namespace
from pathlib import Path
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[1]
CIJOE_VENV_SITEPACKAGES = (
    Path(shutil.which("cijoe")).resolve().parent.parent
    / "lib"
    / f"python{sys.version_info.major}.{sys.version_info.minor}"
    / "site-packages"
)
sys.path.insert(0, str(CIJOE_VENV_SITEPACKAGES))
sys.path.insert(0, str(REPO / "scripts"))

import bench_visualize  # noqa: E402
import fio_compare_collect  # noqa: E402


LABEL = "Not using thread siblings; SMT on; stress off; turbo on"


def _make_row(*, rw: str, backend: str, iosize: int, qdepth: int, rep: int) -> dict:
    base = 1000 + iosize // 4096 * 100 + qdepth * 10 + (0 if backend == "spdk" else 500)
    return {
        "thr_sib": False,
        "ndevs": 1,
        "cpu_usage": 50 + rep + (0 if backend == "spdk" else 2),
        "device_bdf": "0000:02:00.0",
        "cpu_governor": "performance",
        "iosize": iosize,
        "fixed_freq": 0,
        "backend": backend,
        "ncpus": 1,
        "smt": 1,
        "qdepth": qdepth,
        "stress": 0,
        "tool": "fio_xnvme",
        "mibs": float(base / 10 + rep),
        "turbo": 1,
        "cpu_control_supported": False,
        "cpu_freqs": [[[5000000 + rep, 0]]],
        "rw": rw,
        "iops": float(base + rep),
        "fio_size": "2GiB",
    }


def _write_raw_workload_dir(root: Path, workload: str) -> Path:
    results_dir = root / workload
    results_dir.mkdir(parents=True, exist_ok=True)

    for iosize in (4096, 16384):
        for qdepth in (1, 4):
            for backend in ("spdk", "upcie"):
                stem = (
                    f"d1-c1-o{iosize}-f_2GiB-rw_{workload}-q{qdepth}"
                    f"-be_{backend}-tool_fio_xnvme-thrsib0-freq_performance-stress0-SMT1-turbo1"
                )
                for rep in range(3):
                    payload = _make_row(
                        rw=workload,
                        backend=backend,
                        iosize=iosize,
                        qdepth=qdepth,
                        rep=rep,
                    )
                    (results_dir / f"{stem}-{rep}.out").write_text(json.dumps(payload))

    return results_dir


def _collect_merged_json(tmp_path: Path) -> Path:
    raw_root = tmp_path / "artifacts" / "fio-compare" / "0000:02:00.0" / "raw"
    read_dir = _write_raw_workload_dir(raw_root, "read")
    randread_dir = _write_raw_workload_dir(raw_root, "randread")
    merged = tmp_path / "artifacts" / "fio-compare" / "0000:02:00.0" / "benchmark-results.json"

    rc = fio_compare_collect.main(
        Namespace(results_dirs=[read_dir, randread_dir], output_path=merged),
        None,
    )
    assert rc == 0
    return merged


# Artifact smoke tests for the compare benchmark.
#
# These tests build fake raw .out files, run the collector to merge them into a
# single benchmark-results.json, and then render the compare HTML from that
# merged JSON. This keeps the collector and visualizer testable without running
# the full benchmark workflow.
class TestFioCompareArtifacts(unittest.TestCase):
    def test_fio_compare_collect_merges_fake_raw_results(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            merged = _collect_merged_json(tmp_path)

            with merged.open() as handle:
                data = json.load(handle)

            self.assertEqual(list(data), [LABEL])
            rows = data[LABEL]
            self.assertEqual(len(rows), 16)
            self.assertEqual({row["rw"] for row in rows}, {"read", "randread"})
            self.assertEqual({row["backend"] for row in rows}, {"spdk", "upcie"})
            self.assertEqual({row["device_bdf"] for row in rows}, {"0000:02:00.0"})
            self.assertEqual({row["cpu_control_supported"] for row in rows}, {False})

    def test_bench_visualize_renders_compare_html_from_merged_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            merged = _collect_merged_json(tmp_path)
            html_path = tmp_path / "artifacts" / "fio-compare" / "0000:02:00.0" / "benchmark-results.html"

            cwd = Path.cwd()
            try:
                os.chdir(REPO)
                rc = bench_visualize.main(
                    Namespace(
                        output=tmp_path,
                        path=merged,
                        html_path=html_path,
                        template="benchmark-fio-compare",
                    ),
                    None,
                )
            finally:
                os.chdir(cwd)

            self.assertEqual(rc, 0)
            self.assertTrue(html_path.exists())

            html = html_path.read_text()
            self.assertIn("FIO xNVMe Backend Compare", html)
            self.assertIn("SPDK", html)
            self.assertIn("uPCIe", html)
            self.assertIn("CPU control warning", html)
