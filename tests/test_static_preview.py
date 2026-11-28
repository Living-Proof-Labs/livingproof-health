# SPDX-License-Identifier: Apache-2.0
"""Local preview entry point and JavaScript trust boundary."""

import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def test_static_loader_boundaries():
    subprocess.run(["node", str(ROOT / "tests/static_preview.cjs")], check=True, timeout=30)


def test_preview_cli_preserves_data_and_reuses_controls(tmp_path):
    raw = json.dumps(
        {
            "format": "livingproof-evaluator-health/1",
            "trials": [
                {
                    "trial": {"run_id": "g1-example", "configuration": "stock", "index": 1},
                    "simulator": {
                        "provenance": "simulator",
                        "sample_count": 1,
                        "snapshots": [{"time_ns": "0"}],
                    },
                }
            ],
        }
    ).encode()
    source = tmp_path / "health.json"
    source.write_bytes(raw)
    output = tmp_path / "preview"
    command = [
        sys.executable,
        str(ROOT / "examples/recorded-replay/preview.py"),
        str(source),
        "--sha256",
        hashlib.sha256(raw).hexdigest(),
        "--run-id",
        "g1-example",
        "--configuration",
        "stock",
        "--trial-index",
        "1",
        "--output",
        str(output),
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert (output / "data/health.json").read_bytes() == raw
    viewer = (output / "viewer.html").read_text()
    assert "<main hidden>" in viewer
    assert "await loadDetails(location.hash, location.href)" in viewer
    assert "textContent" in viewer and "innerHTML" not in viewer
    assert "g1-example" not in viewer  # Static executable shell has no trial data.
    assert "connect-src 'self'" in viewer
    assert "Local G1 card preview" in (output / "index.html").read_text()
    again = subprocess.run(command, capture_output=True, text=True, timeout=30)
    assert again.returncode == 2
    assert (output / "data/health.json").read_bytes() == raw
