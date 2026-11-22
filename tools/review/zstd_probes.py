# SPDX-License-Identifier: Apache-2.0
"""Implementor reconstruction of #13 comment 7017492431; NOT independent review."""

import hashlib
import json
import os
from pathlib import Path
import resource
import subprocess
import sys
import tempfile
import time
import traceback
import xml.etree.ElementTree as ET

CASES = [
    f"{revision}_{size}_{tail}"
    for revision in ("candidate", "old")
    for size in ("known", "unknown")
    for tail in ("prefix", "empty", "skippable", "valid")
]
OLD = "6f6527aad72684fb68d9271bc58149d6617c7fba"
ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "artifacts/review-zstd"
PROVENANCE = "Implementor reconstruction from reviewer specification recovered from recorded tool-call history (#13 comment 7021500386), not byte-for-byte original script recovery. Implementor execution is not independent verification."


def containment(*, offline=True):
    assert Path("/.dockerenv").exists(), "Docker required"
    base = Path("/sys/fs/cgroup")
    values = {
        key: (base / key).read_text().strip()
        for key in ("memory.max", "memory.swap.max", "cpu.max", "pids.max")
    }
    assert int(values["memory.max"]) == 512 << 20
    assert int(values["memory.swap.max"]) == 0
    quota, period = map(int, values["cpu.max"].split())
    assert quota == 2 * period
    assert int(values["pids.max"]) == 128
    values["network_interfaces"] = sorted(p.name for p in Path("/sys/class/net").iterdir())
    if offline:
        assert values["network_interfaces"] == ["lo"], "Loopback-only network required"
    return values


def environment():
    # No CI credentials or arbitrary inherited environment reaches CLI children.
    return {"PATH": os.environ["PATH"], "HOME": "/tmp", "LANG": "C.UTF-8"}


def worker(case):
    observed = containment()
    resource.setrlimit(resource.RLIMIT_AS, (256 << 20, 256 << 20))
    resource.setrlimit(resource.RLIMIT_CPU, (8, 8))
    started = time.monotonic()
    # Fixture generation and all third-party parsing happen after containment checks.
    import struct
    import zlib

    from mcap.data_stream import RecordBuilder
    from mcap.records import Channel, Chunk, DataEnd, Footer, Header, Message, Schema
    import zstandard

    revision, size, suffix = case.split("_")

    def encode(*records):
        builder = RecordBuilder()
        for record in records:
            record.write(builder)
        return builder.end()

    raw = encode(
        Schema(1, b"{}", "jsonschema", "foxglove.PoseInFrame"),
        Channel(id=1, schema_id=1, topic="/base_pose", message_encoding="json", metadata={}),
        Message(1, 1, b"{}", 1, 1),
    )
    frame = zstandard.ZstdCompressor(write_content_size=size == "known").compress(raw)
    tail = {
        "prefix": zstandard.ZstdCompressor().compress(raw)[:5],
        "empty": zstandard.ZstdCompressor().compress(b""),
        "skippable": struct.pack("<II", 0x184D2A50, 4) + b"abcd",
        "valid": b"",
    }[suffix]
    crc = zlib.crc32(raw)
    assert crc == 572566889
    magic = b"\x89MCAP0\r\n"
    fixture = (
        magic
        + encode(
            Header("", "probe"),
            Chunk("zstd", frame + tail, 1, 1, crc, len(raw)),
            DataEnd(0),
            Footer(0, 0, 0),
        )
        + magic
    )
    if size == "unknown" and suffix == "prefix":
        assert len(fixture) == 246
    (OUT / f"{case}.mcap").write_bytes(fixture)
    calls = []
    with tempfile.TemporaryDirectory() as directory:
        folder = Path(directory) / "data"
        folder.mkdir()
        cli_env = environment()
        source_root = ROOT / "src"
        if revision == "old":
            source_root = Path(directory) / "old-src"
            files = subprocess.check_output(
                ["git", "ls-tree", "-r", "--name-only", OLD, "src/livingproof_health"],
                cwd=ROOT,
                text=True,
            ).splitlines()
            assert files, "Old source unavailable"
            for name in files:
                destination = source_root / Path(name).relative_to("src")
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(
                    subprocess.check_output(["git", "show", f"{OLD}:{name}"], cwd=ROOT)
                )
        cli_env["PYTHONPATH"] = str(source_root)
        source_digest = hashlib.sha256(
            (source_root / "livingproof_health/bounds.py").read_bytes()
        ).hexdigest()
        source, target, config = (
            folder / name for name in ("probe.mcap", "replay.json", "limits.json")
        )
        source.write_bytes(fixture)
        config.write_text(
            json.dumps({"expanded_chunk_bytes": len(raw)} if suffix == "valid" else {})
        )
        target.write_bytes(b"existing complete result")
        for output in ([], ["--output", str(target)]):
            command = [
                str(Path(sys.executable).with_name("livingproof-health")),
                "replay",
                str(source),
                "--limits",
                str(config),
                *output,
            ]
            result = subprocess.run(command, env=cli_env, capture_output=True, text=True, timeout=4)
            calls.append(
                {
                    "command": command,
                    "returncode": result.returncode,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                }
            )
            if suffix == "valid" or (revision == "old" and size == "unknown"):
                assert result.returncode == 0, calls
                text = target.read_text() if output else result.stdout
                doc = json.loads(text)
                assert len(doc["snapshots"]) == 1
                assert doc["snapshots"][0]["time_ns"] == "1"
                if output:
                    assert result.stdout == "" and text == calls[0]["stdout"]
            else:
                assert result.returncode != 0 and result.stdout == "", calls
                assert "zstd" in result.stderr, calls
                assert target.read_bytes() == b"existing complete result"
            calls[-1].update(
                target_hex=target.read_bytes().hex(),
                temporary_files=[p.name for p in folder.glob(".health-*")],
                assertions_passed=True,
            )
            assert sorted(p.name for p in folder.iterdir()) == [
                "limits.json",
                "probe.mcap",
                "replay.json",
            ]
    return {
        "case": case,
        "bounds_source_sha256": source_digest,
        "revision": revision,
        "outcome": "PASS",
        "cgroup": observed,
        "input_sha256": hashlib.sha256(fixture).hexdigest(),
        "input_bytes": len(fixture),
        "expanded_bytes": len(raw),
        "calls": calls,
        "elapsed_s": time.monotonic() - started,
        "worker_peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "descendant_peak_rss_kib": resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,
        "address_space_bytes": 256 << 20,
        "cpu_seconds": 8,
        "wall_seconds": 12,
    }


def main():
    observed = containment()
    OUT.mkdir(parents=True, exist_ok=True)
    assert not list(OUT.glob("*.json")), "Use a fresh evidence directory"

    def git(*args):
        return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()

    expected = os.environ["REVIEW_HEAD"]
    identity = {
        "requested_head": expected,
        "old_commit": OLD,
        "old_tree": git("rev-parse", f"{OLD}^{{tree}}"),
        "checkout_commit": git("rev-parse", "HEAD"),
        "checkout_tree": git("rev-parse", "HEAD^{tree}"),
        "head_tree": git("rev-parse", f"{expected}^{{tree}}"),
        "probe_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    assert identity["checkout_tree"] == identity["head_tree"], (
        "Checkout differs from requested head tree"
    )
    results = []
    for case in CASES:
        started = time.monotonic()
        command = [sys.executable, str(Path(__file__).resolve()), case]
        try:
            result = subprocess.run(
                command, env=environment(), capture_output=True, text=True, timeout=12
            )
            (OUT / f"{case}.log").write_text(
                f"command: {command!r}\nexit: {result.returncode}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
            )
            assert result.returncode == 0, result.stderr
            record = json.loads(result.stdout)
            assert record["case"] == case and record["outcome"] == "PASS"
        except Exception:
            record = {"case": case, "outcome": "FAIL", "error": traceback.format_exc()}
        record.update(
            identity=identity, provenance=PROVENANCE, subprocess_wall_s=time.monotonic() - started
        )
        (OUT / f"{case}.json").write_text(json.dumps(record, indent=2) + "\n")
        results.append(record)
    # Existing regression evidence remains separate and must still be complete.
    cases = ET.parse(ROOT / "artifacts/tests.xml").findall(".//testcase")
    resources = list((ROOT / "artifacts/bounds").glob("*.json"))
    existing_ok = (
        len(cases) == 244  # 240 release-branch cases plus four visual replay cases.
        and all(
            not any(c.find(tag) is not None for tag in ("failure", "error", "skipped"))
            for c in cases
        )
        and len(resources) == 41
        and all(json.loads(p.read_text())["outcome"] == "PASS" for p in resources)
    )
    complete = {p.stem for p in OUT.glob("*.json")} == set(CASES)
    passed = complete and existing_ok and all(r["outcome"] == "PASS" for r in results)
    summary = {
        "provenance": PROVENANCE,
        "identity": identity,
        "cgroup": observed,
        "expected_cases": CASES,
        "existing_tests": len(cases),
        "junit_sha256": hashlib.sha256((ROOT / "artifacts/tests.xml").read_bytes()).hexdigest(),
        "resource_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in resources},
        "existing_resource_records": len(resources),
        "complete": complete,
        "outcome": "PASS" if passed else "FAIL",
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    assert passed, "Review probe coverage/assertions or existing evidence failed"


if __name__ == "__main__":
    if len(sys.argv) == 2:
        assert sys.argv[1] in CASES
        print(json.dumps(worker(sys.argv[1])))
    else:
        main()
