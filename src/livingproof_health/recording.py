# SPDX-License-Identifier: Apache-2.0
"""An explicit adapter for the simulation recorder's JSON base pose channel."""

import json
import math
from pathlib import Path
from typing import Protocol

from mcap.records import Schema, Channel, Message

from .bounds import Limits, Meter, records, json_payload, replay_json

from .snapshots import Replay, snapshot, snapshot_to_wire


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


def read_mcap(path, *, topic="/base_pose", limits=None):
    """Bounded, CRC-checked file-order input; stable log-time output, no decimation."""
    limits = limits or Limits()
    path = Path(path)
    adapter = BasePoseAdapter()
    samples, schemas, channels = [], {}, {}
    meter = Meter(limits)
    with records(path, limits) as (entries, digest):
        for record in entries:
            if isinstance(record, Schema):
                if record.id in schemas and schemas[record.id] != record:
                    raise ValueError("Conflicting MCAP schema id")
                schemas[record.id] = record
            elif isinstance(record, Channel):
                if record.id in channels and channels[record.id] != record:
                    raise ValueError("Conflicting MCAP channel id")
                if record.schema_id and record.schema_id not in schemas:
                    raise ValueError("MCAP channel refers to an unknown schema")
                channels[record.id] = record
            elif isinstance(record, Message):
                channel = channels.get(record.channel_id)
                if channel is None:
                    raise ValueError("MCAP message refers to an unknown channel")
                if channel.topic != topic:
                    continue
                schema = schemas.get(channel.schema_id)
                if (
                    schema is None
                    or schema.name != "foxglove.PoseInFrame"
                    or schema.encoding != "jsonschema"
                    or channel.message_encoding != "json"
                ):
                    raise ValueError(
                        "Selected topic requires foxglove.PoseInFrame JSON schema/messages"
                    )
                meter.add("snapshots", 1)
                sample = adapter.observe(record.log_time, json_payload(record.data, limits))
                sample["source"] = {
                    "sha256": "0" * 64,
                    "topic": topic,
                    "clock": "mcap-log-time",
                    "publish_time_ns": record.publish_time,
                    "sequence": record.sequence,
                    "adapter": "base-pose-json/1",
                    "evidence": "recorded-observation; hardware origin not established",
                }
                retained = json.dumps(
                    snapshot_to_wire(sample), sort_keys=True, separators=(",", ":"), allow_nan=False
                ).encode()
                meter.add("retained_bytes", len(retained))
                samples.append(sample)
        source_hash = digest.hexdigest()
    if not samples:
        raise ValueError(f"No pose messages on selected topic {topic!r}; choose --topic explicitly")
    for sample in samples:
        sample["source"]["sha256"] = source_hash
    replay = Replay(samples)
    # API callers get the same output guarantee as the CLI, before a result is returned.
    with replay_json(replay, limits):
        pass
    return replay
