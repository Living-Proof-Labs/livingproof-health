# SPDX-License-Identifier: Apache-2.0
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from livingproof_health.indicator import sampled_height_indicator
from livingproof_health.snapshots import Replay

CRITERION = {"minimum_m": 0.5, "frame_id": "world", "source": "explicit test criterion"}


def sample(time, height, frame="world"):
    return {
        "time_ns": time,
        "items": {"base_pose": {"position": {"z": height}, "unit": "m", "frame_id": frame}},
    }


@pytest.mark.parametrize(
    "height,state",
    [(0.49, "below-threshold"), (0.5, "at-or-above-threshold"), (0.51, "at-or-above-threshold")],
)
def test_boundary(height, state):
    result = sampled_height_indicator(
        Replay([sample(0, height), sample(20, height)]), criterion=CRITERION
    )
    assert result["state"] == state
    assert result["minimum_m"] == height
    assert result["time_ns"] == "0"
    assert result["orientation"] == "not-evaluated"
    assert result["whole_trial_parity"] == "not-established"


def test_interior_sampled_dip_is_not_hidden_by_endpoints():
    result = sampled_height_indicator(
        Replay([sample(0, 0.8), sample(20, 0.4), sample(40, 0.8)]), criterion=CRITERION
    )
    assert (result["state"], result["time_ns"], result["minimum_m"]) == (
        "below-threshold",
        "20",
        0.4,
    )


@pytest.mark.parametrize(
    "rows", [[], [{"time_ns": 0}], [sample(0, 0.8)], [sample(0, 0.8, "other"), sample(20, 0.8)]]
)
def test_missing_or_incomplete_evidence_is_unevaluated(rows):
    assert sampled_height_indicator(Replay(rows), criterion=CRITERION)["state"] == "unevaluated"


def test_no_criterion_is_not_applicable_even_with_low_height():
    assert (
        sampled_height_indicator(Replay([sample(0, 0.1), sample(20, 0.1)]))["state"]
        == "not-applicable"
    )


def test_missing_sample_cannot_erase_observed_violation():
    result = sampled_height_indicator(
        Replay([sample(0, 0.4), {"time_ns": 20}]), criterion=CRITERION
    )
    assert result["state"] == "below-threshold"
    assert result["unavailable_count"] == 1


@pytest.mark.parametrize(
    "criterion", [{**CRITERION, "minimum_m": float("nan")}, {**CRITERION, "source": ""}]
)
def test_invalid_explicit_criterion_is_not_a_default(criterion):
    with pytest.raises(ValueError):
        sampled_height_indicator(Replay([]), criterion=criterion)


def test_real_demo_entry_point_criterion_and_omission(tmp_path):
    rows = json.loads(Replay([sample(0, 0.8), sample(20, 0.7)]).to_json())["snapshots"]
    raw = json.dumps(
        {
            "format": "livingproof-evaluator-health/1",
            "trials": [
                {
                    "trial": {"run_id": "test", "configuration": "stock", "index": 1},
                    "simulator": {"provenance": "simulator", "sample_count": 2, "snapshots": rows},
                }
            ],
        }
    ).encode()
    source = tmp_path / "health.json"
    source.write_bytes(raw)
    script = Path(__file__).resolve().parents[1] / "examples/recorded-height/demo.py"
    base = [
        sys.executable,
        str(script),
        str(source),
        "--sha256",
        hashlib.sha256(raw).hexdigest(),
        "--run-id",
        "test",
        "--configuration",
        "stock",
        "--trial-index",
        "1",
    ]
    for label, flags in [
        (
            "present",
            ["--minimum-m", "0.5", "--frame-id", "world", "--criterion-source", "test <script>"],
        ),
        ("absent", []),
    ]:
        output = tmp_path / label
        result = subprocess.run(
            base + flags + ["--output", str(output)], capture_output=True, text=True, timeout=30
        )
        assert result.returncode == 0, result.stderr
        indicator = json.loads((output / "indicator.json").read_text())
        assert indicator["state"] == ("at-or-above-threshold" if flags else "not-applicable")
        page = (output / "index.html").read_text()
        assert "<script>" not in page
        assert "viewer.html" in page and "not orientation" in page
    assert source.read_bytes() == raw
