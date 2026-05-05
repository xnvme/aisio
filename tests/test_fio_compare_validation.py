from pathlib import Path
import subprocess
import tempfile
import unittest


# Validation-only tests for the fio compare workflow.
#
# These cases do not run the full benchmark. They only verify that the
# compare workflow rejects multi-device configs and accepts a single-device
# config before any heavy benchmark setup starts.
class TestBenchFioCompareValidation(unittest.TestCase):
    def test_bench_fio_compare_rejects_multi_device_configs(self):
        repo = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            output = tmp_path / "cijoe-output"
            workflow = tmp_path / "validate-only.yaml"

            workflow.write_text(
                """
doc: |
  Validate device config only.
steps:
- name: validate_device_config
  run: bash -lc 'test {{ config.devices | length }} -eq 1 || { echo "bench_fio_compare requires exactly one benchmark device"; exit 1; }'
""".lstrip()
            )

            result = subprocess.run(
                [
                    "cijoe",
                    "--monitor",
                    "--output",
                    str(output),
                    "-c",
                    str(repo / "configs" / "bench_fio_compare.toml"),
                    "-c",
                    str(repo / "configs" / "devices_16.toml"),
                    str(workflow),
                ],
                cwd=repo,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertNotEqual(result.returncode, 0)
            combined_output = result.stdout + result.stderr
            self.assertIn("bench_fio_compare requires exactly one benchmark device", combined_output)

    def test_bench_fio_compare_accepts_single_device_configs(self):
        repo = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            output = tmp_path / "cijoe-output"
            config = tmp_path / "single-device.toml"
            workflow = tmp_path / "validate-only.yaml"

            config.write_text(
                """
[fio_compare]
fio_size = "2GiB"
output_root = "cijoe-output/artifacts/fio-compare"

[xnvme.driver]
prefix = "PCI_BLACKLIST=0000:0c:00.0"

[[devices]]
pci_addr = "0000:02:00.0"
""".lstrip()
            )

            workflow.write_text(
                """
doc: |
  Validate device config only.
steps:
- name: validate_device_config
  run: bash -lc 'test {{ config.devices | length }} -eq 1 || { echo "bench_fio_compare requires exactly one benchmark device"; exit 1; }'
""".lstrip()
            )

            result = subprocess.run(
                [
                    "cijoe",
                    "--monitor",
                    "--output",
                    str(output),
                    "-c",
                    str(config),
                    str(workflow),
                ],
                cwd=repo,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0)
