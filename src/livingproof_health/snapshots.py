# SPDX-License-Identifier: Apache-2.0
"""Portable observations. No robot morphology or health policy lives here."""

from bisect import bisect_left
from copy import deepcopy
import json
import re

FORMAT = "livingproof-health/1"


def timestamp(value):
    if type(value) is not int or value < 0:
        raise ValueError("time_ns must be a nonnegative integer (nanoseconds)")
    return value


def timestamp_to_wire(value):
    """JSON numbers cannot preserve epoch nanoseconds in ordinary JavaScript."""
    return str(timestamp(value))


def timestamp_from_wire(value):
    """Accept canonical nonnegative ASCII decimal strings only, never numbers."""
    if not isinstance(value, str) or re.fullmatch(r"0|[1-9][0-9]*", value) is None:
        raise ValueError("Timestamp must be a canonical nonnegative decimal string, e.g. '0'")
    return int(value)


def snapshot_to_wire(value):
    result = snapshot(value)
    result["time_ns"] = timestamp_to_wire(result["time_ns"])
    source = result.get("source")
    if isinstance(source, dict) and "publish_time_ns" in source:
        source["publish_time_ns"] = timestamp_to_wire(source["publish_time_ns"])
    return result


def snapshot_from_wire(value):
    if not isinstance(value, dict) or "time_ns" not in value:
        raise ValueError("Expected a snapshot object with time_ns")
    result = deepcopy(value)
    result["time_ns"] = timestamp_from_wire(result["time_ns"])
    source = result.get("source")
    if isinstance(source, dict) and "publish_time_ns" in source:
        source["publish_time_ns"] = timestamp_from_wire(source["publish_time_ns"])
    return snapshot(result)


def snapshot(value):
    """Validate and copy a snapshot; only time_ns is required.

    Items are arbitrary JSON values keyed by adapter-owned names. An absent key
    means not reported; null means explicitly unavailable. Neither means healthy.
    Additional JSON fields are retained for robot identity or source metadata.
    """
    if not isinstance(value, dict) or "time_ns" not in value:
        raise ValueError("Expected a snapshot object with time_ns")
    timestamp(value["time_ns"])
    source = value.get("source")
    if isinstance(source, dict) and "publish_time_ns" in source:
        timestamp(source["publish_time_ns"])
    if "items" in value and not isinstance(value["items"], dict):
        raise ValueError("items must be an object; use null values for unavailable items")

    # Check the whole tree, including metadata: no NaN, infinity, or non-JSON types.
    def validate(node):
        if isinstance(node, dict):
            if any(not isinstance(key, str) for key in node):
                raise ValueError("JSON object keys must be strings")
            for child in node.values():
                validate(child)
        elif isinstance(node, list):
            for child in node:
                validate(child)
        elif node is not None and type(node) not in (str, int, float, bool):
            raise ValueError("Snapshot values must be JSON values")

    validate(value)
    json.dumps(value, allow_nan=False)
    return deepcopy(value)


class Replay:
    """Stable time order, with duplicate timestamps kept in source order.

    seek returns the first sample at or after the requested time, never a stale
    carried-forward value or interpolated observation. It returns None past end.
    Returned values are copies so a consumer cannot change subsequent replay.
    """

    def __init__(self, snapshots):
        self._samples = sorted((snapshot(s) for s in snapshots), key=lambda s: s["time_ns"])
        self._times = [s["time_ns"] for s in self._samples]

    def __iter__(self):
        return iter(deepcopy(self._samples))

    def seek(self, time_ns):
        index = bisect_left(self._times, timestamp(time_ns))
        return deepcopy(self._samples[index]) if index < len(self._samples) else None

    def to_json(self):
        return (
            json.dumps(
                {"format": FORMAT, "snapshots": [snapshot_to_wire(s) for s in self._samples]},
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
            + "\n"
        )

    @classmethod
    def from_json(cls, text):
        doc = json.loads(text)
        if not isinstance(doc, dict) or doc.get("format") != FORMAT:
            raise ValueError(f"Expected format {FORMAT!r}")
        if not isinstance(doc.get("snapshots"), list):
            raise ValueError("snapshots must be an array")
        return cls(snapshot_from_wire(s) for s in doc["snapshots"])
