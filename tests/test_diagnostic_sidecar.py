# SPDX-License-Identifier: Apache-2.0
"""Offline evidence regression, using the actual pinned evaluator."""

import copy
import gzip
import hashlib
import json
from pathlib import Path
import runpy

from livingproof_evaluator_scenario import EVALUATE
import pytest

from livingproof_health.assessment import assess_base_height
from livingproof_health.recording import read_mcap
from livingproof_health.snapshots import Replay

ROOT = Path(__file__).parent / "fixtures"
DIAGNOSTIC = ROOT / "diagnostic-sidecar"
ORIGINAL = ROOT / "original-recording"
gaps = runpy.run_path(str(ROOT.parents[1] / "tools/diagnostic-sidecar/coverage.py"))["gaps"]


def sidecar():
    return json.loads(gzip.decompress((DIAGNOSTIC / "sidecar.json.gz").read_bytes()))


def test_diagnostic_pairing_and_repeat():
    provenance = json.loads((DIAGNOSTIC / "provenance.json").read_text())
    for name, expected in provenance["files"].items():
        assert hashlib.sha256((DIAGNOSTIC / name).read_bytes()).hexdigest() == expected
    evidence = sidecar()
    for key, name in [
        ("observation_sha256", "evidence/trials/trial-01.json"),
        ("mcap_sha256", "media/mcap/trial-01.mcap"),
    ]:
        assert evidence[key] == hashlib.sha256((ORIGINAL / name).read_bytes()).hexdigest()
    for log in ["generation.log", "repeat.log"]:
        text = (DIAGNOSTIC / log).read_text()
        assert evidence["observation_sha256"] in text
        assert provenance["files"]["sidecar.json.gz"] in text
        assert "1 MCAP recordings (214645 B), all matching their evidence" in text


def test_callback_cadence_initial_early_stop_and_freshness():
    evidence = sidecar()
    rows = evidence["rows"]
    assert evidence["end"] == "crossed_exit"
    assert evidence["timestep_s"] == 0.002
    assert len(rows) == 6131
    assert [r["index"] for r in rows] == list(range(6131))
    assert [int(r["time_ns"]) for r in rows] == list(range(0, 12_260_000_001, 2_000_000))
    assert gaps(evidence) == ["raw position stale at callback time"]
    assert rows[0]["raw_z"] == rows[0]["fresh_z"]
    # Derived positions at callback i correspond to qpos at i-1 for this split-step policy.
    assert all(b["raw_z"] == a["fresh_z"] for a, b in zip(rows, rows[1:]))
    assert rows[-1]["time_s"] == evidence["final_time_s"]


@pytest.mark.parametrize(
    "damage,expected",
    [
        ("empty", "no callbacks"),
        ("initial", "missing initial state"),
        ("cadence", "callback cadence gap"),
        ("terminal", "missing terminal state"),
        ("time", "timestamp mismatch"),
        ("nonfinite", "nonfinite position"),
    ],
)
def test_coverage_gap_detection(damage, expected):
    evidence = copy.deepcopy(sidecar())
    if damage == "empty":
        evidence["rows"] = []
    elif damage == "initial":
        evidence["rows"].pop(0)
    elif damage == "cadence":
        evidence["rows"].pop(100)
    elif damage == "terminal":
        evidence["final_time_s"] += evidence["timestep_s"]
    elif damage == "time":
        evidence["rows"][3]["time_ns"] = "7"
    else:
        evidence["rows"][3]["fresh_z"] = float("nan")
    assert expected in gaps(evidence)


def test_extrema_precision_and_actual_verdicts():
    evidence = sidecar()
    observation = json.loads((ORIGINAL / "evidence/trials/trial-01.json").read_text())
    run = json.loads((ORIGINAL / "evidence/run-manifest.json").read_text())
    parameters = {**run["parameters"], "half_width": 0.75}
    assert parameters["fall_height"] == 0.5
    saved = EVALUATE["hallway-fall"](observation, parameters, "saved")
    recorded = assess_base_height(
        read_mcap(ORIGINAL / "media/mcap/trial-01.mcap"), minimum_m=0.5, frame_id="world"
    )
    assert saved["status"] == recorded["status"] == "PASS"
    assert saved["details"]["observed"] == 0.7464
    assert recorded["minimum_m"] == 0.74637
    for key in ["raw_z", "fresh_z"]:
        low = min(evidence["rows"], key=lambda r: r[key])
        assert low[key] == 0.7463695705647768
        assert low["time_ns"] == {"raw_z": "4440000000", "fresh_z": "4438000000"}[key]
        high = max(evidence["rows"], key=lambda r: r[key])
        assert (high[key], high["time_ns"]) == (0.785, "0")
        oracle = EVALUATE["hallway-fall"](
            {"min_base_height": {"value": low[key], "time": low["time_s"]}}, parameters, key
        )
        replay = Replay(
            [
                {
                    "time_ns": int(r["time_ns"]),
                    "items": {
                        "base_pose": {"frame_id": "world", "unit": "m", "position": {"z": r[key]}}
                    },
                }
                for r in evidence["rows"]
            ]
        )
        health = assess_base_height(replay, minimum_m=0.5, frame_id="world")
        assert oracle["status"] == health["status"] == "PASS"
        assert health["minimum_m"] == oracle["details"]["observed"] == low[key]
        assert health["time_ns"] == int(low["time_ns"])
        assert Replay.from_json(replay.to_json()).to_json() == replay.to_json()
        assert low[key] != recorded["minimum_m"]
        assert health["whole_trial_parity"] == "not-established"


def test_normal_recorder_samples_raw_hook_not_fresh_state():
    rows = sidecar()["rows"][::10]
    recorded = list(read_mcap(ORIGINAL / "media/mcap/trial-01.mcap"))
    assert len(rows) == len(recorded) == 614
    for row, pose in zip(rows, recorded):
        assert int(row["time_ns"]) == pose["time_ns"]
        assert round(row["raw_z"], 5) == pose["items"]["base_pose"]["position"]["z"]
