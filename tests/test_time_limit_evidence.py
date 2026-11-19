# SPDX-License-Identifier: Apache-2.0
"""Authentic time-limit evidence, distinct from synthetic gap injection tests."""

import gzip
import hashlib
import json
from pathlib import Path
import runpy

from livingproof_health.snapshots import Replay

ROOT = Path(__file__).parent / "fixtures/time-limit"
REPO = ROOT.parents[2]


def evidence():
    return json.loads(gzip.decompress((ROOT / "sidecar.json.gz").read_bytes()))


def test_authentic_time_limit_hashes_and_repeat():
    provenance = json.loads((ROOT / "provenance.json").read_text())
    for name, checksum in provenance["files"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == checksum
    for name, checksum in provenance["tools"].items():
        assert hashlib.sha256((REPO / name).read_bytes()).hexdigest() == checksum
    data = evidence()
    assert (
        hashlib.sha256((ROOT / "observation.json").read_bytes()).hexdigest()
        == data["observation_sha256"]
    )
    assert (
        data["observation_sha256"]
        != "8337886b0509110df270dc34c6a78d6c3632dad46c05aac733f55a2e813f5424"
    )
    for name in ["generation.log", "repeat.log"]:
        log = (ROOT / name).read_text()
        assert (
            "hook-disabled/enabled observation bytes identical " + data["observation_sha256"] in log
        )
        assert provenance["files"]["sidecar.json.gz"] in log
        assert "end time_limit callbacks 51 integrations 51" in log


def test_supported_trial_input_changes_duration_only():
    data = evidence()
    assert data["configured_duration_s"] == 0.1
    assert data["previous_configured_duration_s"] == 27.0
    original = json.loads(
        (ROOT.parent / "original-recording/evidence/run-manifest.json").read_text()
    )
    # Retain the original scenario limits; only the trial execution duration differs.
    for name, value in data["parameters"].items():
        if name != "time_limit":
            assert original["parameters"][name] == value


def test_actual_exhaustion_not_exit_or_nonfinite_stop():
    data = evidence()
    observation = json.loads((ROOT / "observation.json").read_text())
    assert data["end"] == observation["end"] == "time_limit"
    assert observation["exit_time"] is None
    assert observation["left_world"] is None
    assert observation["duration_s"] == 0.1
    assert observation["min_base_height"]["value"] > data["parameters"]["fall_height"]
    # Observer has no fall-triggered stop. Complete integration sequence corroborates exhaustion.
    assert len(data["integration_calls"]) == round(0.1 / data["timestep_s"]) + 1


def test_empirical_terminal_gap_matches_actual_integration_events():
    data = evidence()
    rows, calls = data["rows"], data["integration_calls"]
    assert data["timestep_s"] == 0.002
    assert [r["index"] for r in rows] == list(range(51))
    assert [r["time_ns"] for r in rows] == [str(n) for n in range(0, 100_000_001, 2_000_000)]
    assert [r["before_ns"] for r in calls] == [r["time_ns"] for r in rows]
    assert [r["after_ns"] for r in calls] == [
        str(n) for n in range(2_000_000, 102_000_001, 2_000_000)
    ]
    for row, call in zip(rows, calls):
        assert row["time_s"] == call["before_s"]
    terminal = data["terminal"]
    assert terminal["time_s"] == data["final_time_s"] == calls[-1]["after_s"]
    assert terminal["time_ns"] == "102000000"
    assert terminal["time_ns"] not in {r["time_ns"] for r in rows}
    gaps = runpy.run_path(str(REPO / "tools/diagnostic-sidecar/coverage.py"))["gaps"]
    assert gaps(data) == ["missing terminal state", "raw position stale at callback time"]


def test_freshness_separate_from_terminal_gap():
    data = evidence()
    rows = data["rows"]
    assert rows[0]["raw_z"] == rows[0]["fresh_z"]
    assert all(b["raw_z"] == a["fresh_z"] for a, b in zip(rows, rows[1:]))
    assert data["terminal"]["raw_z"] == rows[-1]["fresh_z"]
    assert data["terminal"]["fresh_z"] != data["terminal"]["raw_z"]
    assert any(row["raw_z"] != row["fresh_z"] for row in rows)


def test_unrounded_diagnostics_and_lossless_wire_times():
    rows = evidence()["rows"]
    assert any(row["fresh_z"] != round(row["fresh_z"], 5) for row in rows)
    replay = Replay(
        [
            {"time_ns": int(row["time_ns"]), "items": {"diagnostic_z": row["fresh_z"]}}
            for row in rows
        ]
    )
    assert Replay.from_json(replay.to_json()).to_json() == replay.to_json()
    assert all(isinstance(row["time_ns"], str) for row in json.loads(replay.to_json())["snapshots"])


def test_observation_sampling_is_separate_from_callback_coverage():
    data = evidence()
    observation = json.loads((ROOT / "observation.json").read_text())
    samples = observation["trace"]["samples"]
    assert len(samples) == 6
    assert [sample[0] for sample in samples] == [0, 0.02, 0.04, 0.06, 0.08, 0.1]
    assert [sample[3] for sample in samples] == [
        round(row["raw_z"], 4) for row in data["rows"][::10]
    ]
