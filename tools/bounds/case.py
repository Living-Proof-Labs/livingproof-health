# SPDX-License-Identifier: Apache-2.0
"""Tiny adversarial cases: invoke only inside a memory-constrained Docker subprocess."""

import hashlib
import json
from pathlib import Path
import resource
import struct
import sys
import tempfile
import time
import zlib

from click.testing import CliRunner
import lz4.frame
from mcap.data_stream import RecordBuilder
from mcap.records import Channel, Chunk, DataEnd, Footer, Header, Message, Schema
import zstandard

from livingproof_health.bounds import Limits, MAGIC, BudgetError
from livingproof_health.cli import health
from livingproof_health.recording import read_mcap

assert Path("/.dockerenv").exists(), "Adversarial cases require Docker"
memory_control = next(
    (
        path
        for path in [
            Path("/sys/fs/cgroup/memory.max"),
            Path("/sys/fs/cgroup/memory/memory.limit_in_bytes"),
        ]
        if path.exists()
    ),
    None,
)
assert memory_control is not None, "Cannot verify container memory ceiling"
container_memory = int(memory_control.read_text().strip())
assert container_memory <= 512 << 20, "Container must have at most 512 MiB memory"
resource.setrlimit(resource.RLIMIT_AS, (256 << 20, 256 << 20))
resource.setrlimit(resource.RLIMIT_CPU, (8, 8))
started = time.monotonic()
name = sys.argv[1]
ROOT = Path(__file__).resolve().parents[2]


def packed(*records):
    builder = RecordBuilder()
    for record in records:
        record.write(builder)
    return builder.end()


def raw(topic="/base_pose", count=2, padding=0):
    payload = json.dumps(
        {
            "frame_id": "world",
            "pose": {"position": {"x": 0, "y": 0, "z": 0.7}},
            "pad": "x" * padding,
        }
    ).encode()
    return packed(
        Schema(1, b'{"type":"object"}', "jsonschema", "foxglove.PoseInFrame"),
        Channel(id=1, schema_id=1, topic=topic, message_encoding="json", metadata={}),
        *(
            Message(1, 1700000000000000000 + i, payload, 1700000000000000001 + i, i)
            for i in range(count)
        ),
    )


def file_bytes(contents, codec="", declared=None, crc=None, copies=1):
    encoded = {
        "zstd": lambda: zstandard.ZstdCompressor(write_content_size=False).compress(contents),
        "lz4": lambda: lz4.frame.compress(contents, store_size=False),
        "": lambda: contents,
    }[codec]()
    chunk = Chunk(
        codec,
        encoded,
        1,
        0,
        zlib.crc32(contents) if crc is None else crc,
        len(contents) if declared is None else declared,
    )
    return (
        MAGIC
        + packed(Header("", "bounded-test"), *([chunk] * copies), DataEnd(0), Footer(0, 0, 0))
        + MAGIC
    )


def refuses(path, limits, match):
    try:
        read_mcap(path, limits=limits)
    except (ValueError, BudgetError) as exc:
        assert match in str(exc), str(exc)
    else:
        raise AssertionError("Over-budget/malformed file was accepted")


with tempfile.TemporaryDirectory() as temp:
    path = Path(temp) / "case.mcap"
    if name == "genuine_compatibility":
        original = ROOT / "tests/fixtures/original-recording/media/mcap/trial-01.mcap"
        text = read_mcap(original).to_json()
        assert (
            hashlib.sha256(text.encode()).hexdigest()
            == "90d8ccc2df0a3c8a81aaea0efcf5af90c3112d4945be95fe6e37a6a742dab77c"
        )
        result = CliRunner().invoke(health, ["replay", str(original)])
        assert result.exit_code == 0 and result.output == text, result.output
    elif name.startswith(("zstd_", "lz4_")):
        codec, case = name.split("_", 1)
        content = raw(padding=4096, topic="/ignored" if "unselected" in case else "/base_pose")
        if case in ("expansion", "unselected_expansion"):
            path.write_bytes(file_bytes(content, codec, declared=1))
            refuses(path, Limits(expanded_chunk_bytes=1024), "expansion")
        elif case == "declared_mismatch":
            path.write_bytes(file_bytes(content, codec, declared=len(content) - 1))
            refuses(path, Limits(), "does not match")
        elif case == "truncated":
            encoded = (
                zstandard.ZstdCompressor().compress(content)
                if codec == "zstd"
                else lz4.frame.compress(content)
            )
            chunk = Chunk(codec, encoded[:-1], 1, 0, 0, len(content))
            path.write_bytes(
                MAGIC + packed(Header("", "test"), chunk, DataEnd(0), Footer(0, 0, 0)) + MAGIC
            )
            refuses(path, Limits(), "chunk")
        else:
            path.write_bytes(file_bytes(content, codec))
            assert len(list(read_mcap(path, limits=Limits(expanded_chunk_bytes=len(content))))) == 2
    elif name == "input":
        path.write_bytes(file_bytes(raw()))
        refuses(path, Limits(input_bytes=path.stat().st_size - 1), "input_bytes")
        assert len(list(read_mcap(path, limits=Limits(input_bytes=path.stat().st_size)))) == 2
    elif name == "compressed_unselected":
        path.write_bytes(file_bytes(raw(topic="/ignored")))
        refuses(path, Limits(compressed_chunk_bytes=64), "chunk")
    elif name == "cumulative_unselected":
        content = raw(topic="/ignored")
        path.write_bytes(file_bytes(content, "zstd", copies=3))
        refuses(path, Limits(expanded_total_bytes=len(content) * 2), "expanded_total_bytes")
    elif name == "chunks":
        path.write_bytes(file_bytes(raw(), copies=3))
        refuses(path, Limits(chunks=2), "chunks")
    elif name == "many_records":
        path.write_bytes(file_bytes(raw(topic="/ignored", count=100)))
        refuses(path, Limits(records=12), "records")
    elif name in ("payload", "payload_unselected", "record"):
        path.write_bytes(
            file_bytes(
                raw(topic="/ignored" if "unselected" in name else "/base_pose", padding=1024)
            )
        )
        refuses(
            path,
            Limits(**{"record_bytes" if name == "record" else "payload_bytes": 512}),
            name.split("_")[0],
        )
    elif name == "unselected_unchunked":
        path.write_bytes(
            MAGIC
            + packed(Header("", "test"))
            + raw(topic="/ignored", padding=1024)
            + packed(DataEnd(0), Footer(0, 0, 0))
            + MAGIC
        )
        refuses(path, Limits(payload_bytes=512), "payload_bytes")
    elif name in ("snapshots", "retained_bytes", "metadata_bytes"):
        path.write_bytes(file_bytes(raw(count=5)))
        refuses(path, Limits(**{name: 1}), name)
    elif name == "crc_unselected":
        path.write_bytes(file_bytes(raw(topic="/ignored"), crc=123))
        refuses(path, Limits(), "CRC")
    elif name == "oversized_field":
        body = struct.pack("<I", 0xFFFFFFFF)
        path.write_bytes(
            MAGIC
            + struct.pack("<BQ", 1, len(body))
            + body
            + packed(DataEnd(0), Footer(0, 0, 0))
            + MAGIC
        )
        refuses(path, Limits(), "enclosing record")
    elif name == "depth":
        data = b'{"extra":' + b"[" * 20 + b"0" + b"]" * 20 + b"}"
        content = packed(
            Schema(1, b"{}", "jsonschema", "foxglove.PoseInFrame"),
            Channel(id=1, schema_id=1, topic="/base_pose", message_encoding="json", metadata={}),
            Message(1, 1, data, 1, 0),
        )
        path.write_bytes(file_bytes(content))
        refuses(path, Limits(json_depth=8), "json_depth")
    elif name == "output_atomic":
        path.write_bytes(file_bytes(raw()))
        expected = read_mcap(path).to_json()
        limits = Path(temp) / "limits.json"
        output = Path(temp) / "out.json"
        output.write_text("old-complete-result")
        for budget in (len(expected.encode()) - 1, 1):
            limits.write_text(json.dumps({"output_bytes": budget}))
            result = CliRunner().invoke(
                health, ["replay", str(path), "--limits", str(limits), "--output", str(output)]
            )
            assert result.exit_code != 0 and "output_bytes" in result.stderr
            assert result.stdout == "" and output.read_text() == "old-complete-result"
            assert not list(Path(temp).glob(".health-*"))
        limits.write_text(json.dumps({"output_bytes": len(expected.encode())}))
        result = CliRunner().invoke(
            health, ["replay", str(path), "--limits", str(limits), "--output", str(output)]
        )
        assert result.exit_code == 0 and result.stdout == ""
        assert output.read_text() == expected
    elif name == "output_replace_failure":
        from unittest.mock import patch

        path.write_bytes(file_bytes(raw()))
        output = Path(temp) / "out.json"
        output.write_text("existing-complete-result")
        with patch("os.replace", side_effect=OSError("simulated publish failure")):
            result = CliRunner().invoke(health, ["replay", str(path), "--output", str(output)])
        assert result.exit_code != 0 and result.stdout == ""
        assert output.read_text() == "existing-complete-result"
        assert not list(Path(temp).glob(".health-*"))
    elif name == "output_amplification":
        payload = json.dumps(
            {"frame_id": "é" * 1000, "pose": {"position": {"x": 0, "y": 0, "z": 0.7}}},
            ensure_ascii=False,
        ).encode()
        content = packed(
            Schema(1, b"{}", "jsonschema", "foxglove.PoseInFrame"),
            Channel(id=1, schema_id=1, topic="/base_pose", message_encoding="json", metadata={}),
            Message(1, 1, payload, 1, 0),
            Message(1, 2, payload, 2, 1),
        )
        path.write_bytes(file_bytes(content))
        refuses(path, Limits(output_bytes=path.stat().st_size), "output_bytes")
    elif name in ("declared_record", "declared_compressed"):
        opcode = 6 if name == "declared_compressed" else 5
        path.write_bytes(
            MAGIC + packed(Header("", "test")) + struct.pack("<BQ", opcode, 1 << 40) + b"x"
        )
        refuses(path, Limits(), "chunk" if opcode == 6 else "record_bytes")
    elif name == "late_crc_no_stdout":
        good = Chunk("", raw(), 1, 0, 0, len(raw()))
        bad = Chunk("", raw(topic="/ignored"), 1, 0, 123, len(raw(topic="/ignored")))
        path.write_bytes(
            MAGIC + packed(Header("", "test"), good, bad, DataEnd(0), Footer(0, 0, 0)) + MAGIC
        )
        result = CliRunner().invoke(health, ["replay", str(path)])
        assert result.exit_code != 0 and result.stdout == "" and "CRC" in result.stderr
    elif name == "time_only_optional":
        content = packed(
            Schema(1, b"{}", "jsonschema", "foxglove.PoseInFrame"),
            Channel(id=1, schema_id=1, topic="/base_pose", message_encoding="json", metadata={}),
            Message(1, 2, b"{}", 2, 0),
            Message(1, 1, b"{}", 1, 1),
            Message(1, 1, b"{}", 1, 2),
        )
        path.write_bytes(file_bytes(content))
        replay = read_mcap(path)
        assert [r["time_ns"] for r in replay] == [1, 1, 2]
        assert replay.seek(1)["source"]["sequence"] == 1
        assert all(r["items"]["base_pose"] is None for r in replay)
    else:
        raise AssertionError(name)
print(
    json.dumps(
        {
            "case": name,
            "container_memory_bytes": container_memory,
            "outcome": "PASS",
            "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            "worker_vm_hwm_kib": int(
                next(
                    line.split()[1]
                    for line in Path("/proc/self/status").read_text().splitlines()
                    if line.startswith("VmHWM:")
                )
            ),
            "elapsed_s": time.monotonic() - started,
            "address_space_limit_bytes": 256 << 20,
            "cpu_limit_s": 8,
        }
    )
)
