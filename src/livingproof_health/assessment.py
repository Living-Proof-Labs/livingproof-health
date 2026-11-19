# SPDX-License-Identifier: Apache-2.0
"""Scenario expectations are separate from observation and replay."""

import json

from .recording import finite_number
from .snapshots import Replay, timestamp_to_wire


def assess_base_height(replay: Replay, *, minimum_m: float, frame_id: str):
    """Compare every recorded sample to a scenario's explicit height expectation.

    Equality passes. A single instant cannot establish a trial minimum. Missing
    evidence prevents PASS, but cannot erase an observed violation. This is only
    a recorded-sample assessment, not an assertion of full simulation-step coverage.
    """
    if not finite_number(minimum_m):
        raise ValueError("minimum_m must be a finite number in metres")
    if not isinstance(frame_id, str) or not frame_id:
        raise ValueError("frame_id must name the scenario's expected coordinate frame")
    samples = list(replay)
    heights = []
    missing = 0
    for sample in samples:
        item = sample.get("items", {}).get("base_pose")
        if (
            not isinstance(item, dict)
            or item.get("frame_id") != frame_id
            or item.get("unit") != "m"
            or not isinstance(item.get("position"), dict)
            or not finite_number(item["position"].get("z"))
        ):
            missing += 1
        else:
            heights.append((item["position"]["z"], sample["time_ns"]))
    lowest = min(heights, key=lambda pair: pair[0]) if heights else None
    if lowest and lowest[0] < minimum_m:
        status = "FAIL"
    elif missing or len({s["time_ns"] for s in samples}) < 2 or not lowest:
        status = "INSUFFICIENT_EVIDENCE"
    else:
        status = "PASS"
    return {
        "status": status,
        "scope": "recorded-samples-only",
        "expectation": {"minimum_m": minimum_m, "frame_id": frame_id},
        "sample_count": len(samples),
        "unavailable_count": missing,
        "minimum_m": lowest[0] if lowest else None,
        "time_ns": lowest[1] if lowest else None,
        "whole_trial_parity": "not-established",
    }


def assessment_to_json(result):
    """Serialize assessment time using the same lossless convention as snapshots."""
    wire = {**result}
    if wire["time_ns"] is not None:
        wire["time_ns"] = timestamp_to_wire(wire["time_ns"])
    return json.dumps(wire, sort_keys=True, allow_nan=False)
