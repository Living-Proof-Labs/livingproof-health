# SPDX-License-Identifier: Apache-2.0
"""Advisory display of an explicit scenario's sampled base-height criterion."""

from .assessment import assess_base_height
from .snapshots import Replay, timestamp_to_wire


def sampled_height_indicator(replay: Replay, *, criterion=None):
    """No implicit criterion, orientation inference, grade or whole-trial verdict.

    criterion contains minimum_m, frame_id and a caller-supplied source label.
    Missing samples prevent an above-threshold conclusion, but cannot erase a
    recorded below-threshold observation. The existing assessment owns that rule.
    """
    result = {
        "state": "not-applicable",
        "criterion": None,
        "minimum_m": None,
        "time_ns": None,
        "frame_id": None,
        "sample_count": None,
        "unavailable_count": None,
        "scope": "recorded-samples-only",
        "whole_trial_parity": "not-established",
        "orientation": "not-evaluated",
    }
    if criterion is None:
        return result
    if not isinstance(criterion, dict) or set(criterion) != {"minimum_m", "frame_id", "source"}:
        raise ValueError("criterion requires minimum_m, frame_id and source")
    if not isinstance(criterion["source"], str) or not criterion["source"].strip():
        raise ValueError("criterion source must identify the scenario/configuration")
    assessed = assess_base_height(
        replay, minimum_m=criterion["minimum_m"], frame_id=criterion["frame_id"]
    )
    result.update(
        state={
            "PASS": "at-or-above-threshold",
            "FAIL": "below-threshold",
            "INSUFFICIENT_EVIDENCE": "unevaluated",
        }[assessed["status"]],
        criterion=dict(criterion),
        minimum_m=assessed["minimum_m"],
        time_ns=timestamp_to_wire(assessed["time_ns"]) if assessed["time_ns"] is not None else None,
        frame_id=criterion["frame_id"],
        sample_count=assessed["sample_count"],
        unavailable_count=assessed["unavailable_count"],
    )
    return result
