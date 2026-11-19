# SPDX-License-Identifier: Apache-2.0
"""Adversarial fixtures execute only in capped child processes inside Docker."""

import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

from livingproof_health.bounds import Limits

ROOT = Path(__file__).resolve().parents[1]
CASES = [
    "genuine_compatibility",
    *[
        f"frame_{size}_{suffix}"
        for size in ("known", "unknown")
        for suffix in ("prefix", "empty", "skippable", "valid")
    ],
    "declared_record",
    "declared_compressed",
    "late_crc_no_stdout",
    "input",
    "compressed_unselected",
    "cumulative_unselected",
    "chunks",
    "many_records",
    "payload",
    "payload_unselected",
    "record",
    "unselected_unchunked",
    "snapshots",
    "retained_bytes",
    "metadata_bytes",
    "crc_unselected",
    "oversized_field",
    "depth",
    "output_atomic",
    "output_replace_failure",
    "output_amplification",
    "time_only_optional",
] + [
    codec + "_" + case
    for codec in ["zstd", "lz4"]
    for case in [
        "expansion",
        "unselected_expansion",
        "declared_mismatch",
        "truncated",
        "near_limit",
    ]
]


@pytest.mark.parametrize("case", CASES)
def test_bounded_recording_in_container(case):
    assert Path("/.dockerenv").exists() and os.environ.get("HEALTH_BOUNDED_TESTS") == "1", (
        "Run task dev:verify: these cases require constrained Docker, not host execution"
    )
    started = time.monotonic()
    result = subprocess.run(
        [sys.executable, str(ROOT / "tools/bounds/case.py"), case],
        capture_output=True,
        text=True,
        timeout=12,
    )
    assert result.returncode == 0, result.stdout + "\n" + result.stderr
    measured = json.loads(result.stdout)
    measured["subprocess_wall_s"] = time.monotonic() - started
    assert measured["outcome"] == "PASS"
    target = ROOT / "artifacts/bounds"
    target.mkdir(parents=True, exist_ok=True)
    (target / f"{case}.json").write_text(json.dumps(measured, indent=2) + "\n")


@pytest.mark.parametrize(
    "override", [{"records": 0}, {"input_bytes": True}, {"json_depth": 129}, {"snapshots": 160001}]
)
def test_budget_configuration_is_bounded(override):
    with pytest.raises(ValueError):
        Limits(**override)
