# SPDX-License-Identifier: Apache-2.0
"""An explicit adapter for the simulation recorder's JSON base pose channel."""

import hashlib
import json
import math
from pathlib import Path
from typing import Protocol

from mcap.reader import make_reader

from .snapshots import Replay, snapshot


class ObservationAdapter(Protocol):
    """Live or recorded producers can map one timestamped payload to a snapshot."""

    def observe(self, time_ns: int, payload: dict) -> dict: ...


def finite_number(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


class BasePoseAdapter:
    """Reports position in metres and orientation; never labels it upright/fallen.

    Caller selects this adapter only for a recorder whose position unit is metres.
    No robot type, limb count, or implicit frame is supplied.
    """

    def observe(self, time_ns, payload):
        if not isinstance(payload, dict):
            raise ValueError("Base pose payload must be a JSON object")
        item = None
        frame = payload.get("frame_id")
        pose = payload.get("pose")
        if isinstance(frame, str) and frame and isinstance(pose, dict):
            position = pose.get("position")
            if isinstance(position, dict) and all(
                finite_number(position.get(axis)) for axis in ("x", "y", "z")
            ):
                item = {"frame_id": frame, "unit": "m", "position": position}
                orientation = pose.get("orientation")
                if isinstance(orientation, dict) and all(
                    finite_number(orientation.get(axis)) for axis in ("x", "y", "z", "w")
                ):
                    item["orientation"] = orientation
        return snapshot({"time_ns": time_ns, "items": {"base_pose": item}})


def read_mcap(path, *, topic="/base_pose"):
    """Read all matching JSON pose messages; order by MCAP log time, then file order.

    No timestamp float conversion, sampling, decimation, interpolation or state
    fusion. Unsupported schemas/encodings on the selected channel are errors.
    """
    path = Path(path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    adapter = BasePoseAdapter()
    samples = []
    with path.open("rb") as stream:
        reader = make_reader(stream, validate_crcs=True)
        for schema, channel, message in reader.iter_messages(topics=[topic], log_time_order=False):
            if (
                schema is None
                or schema.name != "foxglove.PoseInFrame"
                or schema.encoding != "jsonschema"
                or channel.message_encoding != "json"
            ):
                raise ValueError(
                    "Selected topic requires foxglove.PoseInFrame JSON schema/messages"
                )
            sample = adapter.observe(message.log_time, json.loads(message.data))
            sample["source"] = {
                "sha256": digest,
                "topic": topic,
                "clock": "mcap-log-time",
                "publish_time_ns": message.publish_time,
                "sequence": message.sequence,
                "adapter": "base-pose-json/1",
                "evidence": "recorded-observation; hardware origin not established",
            }
            samples.append(sample)
    if not samples:
        raise ValueError(f"No pose messages on selected topic {topic!r}; choose --topic explicitly")
    return Replay(samples)
