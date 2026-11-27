# SPDX-License-Identifier: Apache-2.0
"""Exercise the local demo entry point with unchanged details bytes."""

import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "examples/recorded-replay/details.py"


def invoke(tmp_path, document, digest=None, run="recorded-run"):
    raw = json.dumps(document).encode()
    source = tmp_path / "health.json"
    source.write_bytes(raw)
    output = tmp_path / "viewer.html"
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            str(source),
            "--sha256",
            digest or hashlib.sha256(raw).hexdigest(),
            "--run-id",
            run,
            "--configuration",
            "stock",
            "--trial-index",
            "1",
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert source.read_bytes() == raw
    return result, output


def document(rows):
    return {
        "format": "livingproof-evaluator-health/1",
        "trials": [
            {
                "trial": {"run_id": "recorded-run", "configuration": "stock", "index": 1},
                "simulator": {
                    "provenance": "simulator",
                    "sample_count": len(rows),
                    "snapshots": rows,
                },
                "robot": {"status": "no robot health telemetry"},
            }
        ],
    }


@pytest.mark.parametrize(
    "rows",
    [
        [],
        [{"time_ns": "4440000000"}],
        [
            {"time_ns": "4440000000", "items": {"base_pose": {"position": {"z": 0.7}}}},
        ],
    ],
)
def test_cli_preserves_observations_without_scenario_comparison(tmp_path, rows):
    result, output = invoke(tmp_path, document(rows))
    assert result.returncode == 0, result.stderr
    html = output.read_text()
    embedded = html.split('<script id="data" type="application/json">')[1].split("</script>")[0]
    data = json.loads(embedded)
    assert data["replay"]["snapshots"] == rows
    assert data["report"]["observations_only"] is True
    assert "no robot health telemetry" in data["report"]["input"]["provenance"]
    assert "connect-src 'none'" in html


@pytest.mark.parametrize(
    "case", ["digest", "trial", "missing", "count", "timestamp", "duplicate", "format"]
)
def test_cli_refuses_invalid_details_without_output(tmp_path, case):
    doc = document([{"time_ns": "0"}])
    sim = doc["trials"][0]["simulator"]
    if case == "missing":
        del sim["snapshots"]
    if case == "count":
        sim["sample_count"] = 2
    if case == "timestamp":
        sim["snapshots"][0]["time_ns"] = 0
    if case == "duplicate":
        doc["trials"] *= 2
    if case == "format":
        doc["format"] = "unknown"
    result, output = invoke(
        tmp_path,
        doc,
        digest="0" * 64 if case == "digest" else None,
        run="wrong" if case == "trial" else "recorded-run",
    )
    assert result.returncode == 2
    assert not output.exists()
