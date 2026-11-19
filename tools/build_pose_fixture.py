# SPDX-License-Identifier: Apache-2.0
"""Reproduce the MCAP fixture offline: uv run python tools/build_pose_fixture.py."""

from decimal import Decimal
import json
from pathlib import Path

from mcap.writer import CompressionType, Writer

ROOT = Path(__file__).resolve().parents[1] / "tests" / "fixtures"


def build(target=ROOT / "simulation-pose.mcap"):
    trace = json.loads((ROOT / "simulation-trace.json").read_text(), parse_float=Decimal)
    provenance = json.loads((ROOT / "provenance.json").read_text())
    with Path(target).open("wb") as stream:
        writer = Writer(stream, compression=CompressionType.NONE)
        writer.start(library="livingproof-health-fixture/1")
        writer.add_metadata("provenance", {k: json.dumps(v) for k, v in provenance.items()})
        schema = writer.register_schema("foxglove.PoseInFrame", "jsonschema", b'{"type":"object"}')
        channel = writer.register_channel("/base_pose", "json", schema)
        for index, (time, x, y, z) in enumerate(trace["samples"]):
            ns = int(time * 1_000_000_000)
            payload = {
                "timestamp": {"sec": ns // 1_000_000_000, "nsec": ns % 1_000_000_000},
                "frame_id": "world",
                "pose": {"position": {"x": float(x), "y": float(y), "z": float(z)}},
            }
            writer.add_message(channel, ns, json.dumps(payload).encode(), ns, sequence=index)
        writer.finish()


if __name__ == "__main__":
    build()
