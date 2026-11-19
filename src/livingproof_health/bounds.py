# SPDX-License-Identifier: Apache-2.0
"""Resource policy and bounded framing around the pinned upstream MCAP decoder."""

from contextlib import contextmanager
from dataclasses import asdict, dataclass, fields
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import struct
import tempfile
import zlib

import lz4.frame
import zstandard
from mcap.records import Channel, Chunk, Message, Schema
from mcap.stream_reader import StreamReader

MAGIC = b"\x89MCAP0\r\n"
BLOCK = 64 * 1024


class BudgetError(ValueError):
    """An explicit recording resource budget was exhausted."""


@dataclass(frozen=True)
class Limits:
    input_bytes: int = 128 << 20
    compressed_chunk_bytes: int = 8 << 20
    expanded_chunk_bytes: int = 8 << 20
    decoder_window_bytes: int = 8 << 20
    expanded_total_bytes: int = 128 << 20
    record_bytes: int = 4 << 20
    payload_bytes: int = 256 << 10
    records: int = 250_000
    chunks: int = 1000
    metadata_bytes: int = 8 << 20
    snapshots: int = 20_000
    retained_bytes: int = 8 << 20
    output_bytes: int = 32 << 20
    json_depth: int = 64

    def __post_init__(self):
        for field in fields(self):
            value = getattr(self, field.name)
            ceiling = field.default * 8 if field.name != "json_depth" else 128
            if type(value) is not int or not 1 <= value <= ceiling:
                raise ValueError(f"{field.name} must be an integer from 1 to {ceiling}")

    @classmethod
    def from_file(cls, path):
        with Path(path).open("rb") as stream:
            data = stream.read(4097)
        if len(data) > 4096:
            raise ValueError("Limits file must be at most 4096 bytes")
        values = json.loads(data)
        if not isinstance(values, dict) or values.keys() - asdict(cls()).keys():
            raise ValueError(
                "Limits file must be an object containing only documented budget names"
            )
        return cls(**values)


def check(name, size, limits):
    maximum = getattr(limits, name)
    if size > maximum:
        raise BudgetError(f"Replay budget {name} exceeded (limit {maximum}); see replay --help")


class Meter:
    def __init__(self, limits):
        self.limits = limits
        self.totals = {}

    def add(self, name, size):
        value = self.totals.get(name, 0) + size
        check(name, value, self.limits)
        self.totals[name] = value


class Input:
    """Single-pass actual-byte hashing/counting; never read an unbounded request."""

    def __init__(self, stream, meter):
        self.stream, self.meter = stream, meter
        self.digest = hashlib.sha256()

    def read(self, size):
        remaining = self.meter.limits.input_bytes - self.meter.totals.get("input_bytes", 0)
        data = self.stream.read(min(size, remaining + 1))
        self.meter.add("input_bytes", len(data))
        self.digest.update(data)
        return data


class Framed:
    """Only one capped record is exposed to upstream field decoders at a time.

    Internal string/data lengths cannot cross the enclosing record or request a
    huge underlying read. Synthetic inner footer is only an iterator terminator.
    """

    def __init__(self, source, meter, *, inner=False):
        self.source, self.meter, self.inner = source, meter, inner
        self.buffer = b""
        self.offset = 0
        self.initial = not inner
        self.trailer = False
        self.length = 0
        self.ended = False
        self.in_body = False
        self.need_header = not inner

    def exact(self, size):
        data = self.source.read(size)
        if len(data) != size:
            raise ValueError("Truncated MCAP record")
        return data

    def read(self, size):
        if size < 0:
            raise ValueError("Unbounded MCAP read refused")
        if size == 0:
            return b""
        if self.offset == len(self.buffer):
            if self.in_body:
                raise ValueError("MCAP field length exceeds enclosing record")
            self.offset = 0
            if self.initial or self.trailer:
                self.initial = False
                self.buffer = MAGIC if self.inner else self.exact(8)
                if self.trailer:
                    self.ended = True
                self.trailer = False
            else:
                head = self.source.read(9)
                if not head and self.inner:
                    # Upstream StreamReader stops on Footer, then consumes magic.
                    self.buffer = struct.pack("<BQ", 2, 20) + bytes(20)
                    self.trailer = True
                    self.length = 0
                else:
                    if len(head) != 9:
                        raise ValueError("Truncated MCAP record header")
                    opcode, length = struct.unpack("<BQ", head)
                    if self.need_header:
                        if opcode != 1:
                            raise ValueError("MCAP must start with a Header record")
                        self.need_header = False
                    self.length = length
                    self.meter.add("records", 1)
                    if self.inner and opcode in range(1, 16) and opcode not in (3, 4, 5):
                        raise ValueError("Invalid record type inside MCAP chunk")
                    if opcode == 6:
                        self.meter.add("chunks", 1)
                        # Fixed fields, compression string (max four bytes), and data length.
                        check("compressed_chunk_bytes", max(0, length - 44), self.meter.limits)
                        if length > self.meter.limits.compressed_chunk_bytes + 44:
                            raise BudgetError("Compressed chunk record exceeds its budget")
                    else:
                        check("record_bytes", length, self.meter.limits)
                    if opcode == 5:
                        if length < 22:
                            raise ValueError("Truncated MCAP message")
                        check("payload_bytes", length - 22, self.meter.limits)
                    if opcode in (3, 4):
                        self.meter.add("metadata_bytes", length)
                    if opcode == 2:
                        self.trailer = True
                    if opcode == 6:
                        if length < 40:
                            raise ValueError("Truncated MCAP chunk header")
                        prefix = self.exact(32)
                        name_length = struct.unpack_from("<I", prefix, 28)[0]
                        if name_length > 4:
                            raise ValueError("Unsupported MCAP compression name")
                        suffix = self.exact(name_length + 8)
                        data_length = struct.unpack_from("<Q", suffix, name_length)[0]
                        check("compressed_chunk_bytes", data_length, self.meter.limits)
                        if length != 40 + name_length + data_length:
                            raise ValueError("MCAP chunk data length exceeds enclosing record")
                        self.buffer = head + prefix + suffix + self.exact(data_length)
                    else:
                        self.buffer = head + self.exact(length)
        remaining = len(self.buffer) - self.offset
        if size > remaining:
            raise ValueError("MCAP field length exceeds enclosing record")
        data = self.buffer[self.offset : self.offset + size]
        self.offset += size
        return data


class GuardedReader(StreamReader):
    """Pinned 1.3.0 hook: keep field reads inside their record, without copying decoders."""

    def __init__(self, framed, **kwargs):
        self.framed = framed
        super().__init__(framed, **kwargs)

    def _read_record(self, opcode, length):
        self.framed.in_body = True
        try:
            return super()._read_record(opcode, length)
        finally:
            self.framed.in_body = False


def expand(chunk, meter):
    """Capped native codec calls; validate actual bytes and CRC before record decode."""
    limits = meter.limits
    check("compressed_chunk_bytes", len(chunk.data), limits)
    check("expanded_chunk_bytes", chunk.uncompressed_size, limits)
    room = min(
        limits.expanded_chunk_bytes,
        limits.expanded_total_bytes - meter.totals.get("expanded_total_bytes", 0),
    )
    if chunk.uncompressed_size > room:
        raise BudgetError("Replay budget expanded_total_bytes exceeded")
    data = bytearray()

    def append(block):
        if len(data) + len(block) > room:
            raise BudgetError("Replay budget actual chunk expansion exceeded")
        data.extend(block)

    if chunk.compression == "zstd":
        try:
            stated = zstandard.frame_content_size(chunk.data)
            if (
                stated not in (zstandard.CONTENTSIZE_UNKNOWN, zstandard.CONTENTSIZE_ERROR)
                and stated > room
            ):
                raise BudgetError("Replay budget zstd frame expansion exceeded")
            check(
                "decoder_window_bytes",
                zstandard.get_frame_parameters(chunk.data).window_size,
                limits,
            )
            # Pinned backend passes this value directly to ZSTD_DCtx_setMaxWindowSize (bytes).
            decoder = zstandard.ZstdDecompressor(max_window_size=limits.decoder_window_bytes)
            with decoder.stream_reader(io.BytesIO(chunk.data), read_across_frames=True) as stream:
                while block := stream.read(min(BLOCK, room + 1 - len(data))):
                    append(block)
            # Stream readers can stop on truncated input without proving frame EOF.
            # A second, bounded single-frame decode checks completion/trailing bytes.
            verified = decoder.decompress(
                chunk.data, max_output_size=max(1, room), allow_extra_data=False
            )
            if verified != data:
                raise ValueError("Inconsistent zstd expansion")
        except zstandard.ZstdError as exc:
            raise ValueError(f"Invalid or over-window zstd chunk: {exc}") from exc
    elif chunk.compression == "lz4":
        try:
            stated = lz4.frame.get_frame_info(chunk.data)["content_size"]
            if stated > room:
                raise BudgetError("Replay budget lz4 frame expansion exceeded")
            decoder = lz4.frame.LZ4FrameDecompressor()
            pending = chunk.data
            while True:
                block = decoder.decompress(pending, max_length=min(BLOCK, room + 1 - len(data)))
                pending = b""
                append(block)
                if decoder.eof:
                    if decoder.unused_data:
                        raise ValueError("Trailing data after lz4 frame")
                    break
                if decoder.needs_input or not block:
                    raise ValueError("Truncated lz4 chunk")
        except RuntimeError as exc:
            raise ValueError(f"Invalid lz4 chunk: {exc}") from exc
    elif chunk.compression == "":
        append(chunk.data)
    else:
        raise ValueError(f"Unsupported MCAP compression {chunk.compression!r}")
    if len(data) != chunk.uncompressed_size:
        raise ValueError("MCAP declared expansion size does not match actual bytes")
    if chunk.uncompressed_crc and zlib.crc32(data) != chunk.uncompressed_crc:
        raise ValueError("MCAP chunk CRC mismatch")
    meter.add("expanded_total_bytes", len(data))
    return data


@contextmanager
def records(path, limits):
    """Yield upstream record objects in physical file order, with a final source hash."""
    meter = Meter(limits)
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0))
    with os.fdopen(descriptor, "rb") as source:
        info = os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode):
            raise ValueError("Replay input must be a regular local file")
        check("input_bytes", info.st_size, limits)
        counted = Input(source, meter)
        framed = Framed(counted, meter)

        def iterate():
            for record in GuardedReader(
                framed,
                emit_chunks=True,
                validate_crcs=True,
                record_size_limit=limits.compressed_chunk_bytes + limits.record_bytes + 44,
            ).records:
                if isinstance(record, Chunk):
                    raw = expand(record, meter)
                    inner = Framed(io.BytesIO(raw), meter, inner=True)
                    for entry in GuardedReader(
                        inner,
                        skip_magic=True,
                        emit_chunks=True,
                        record_size_limit=limits.record_bytes,
                    ).records:
                        if isinstance(entry, (Schema, Channel, Message)):
                            yield entry
                else:
                    yield record
            if counted.read(1):
                raise ValueError("Trailing bytes after MCAP closing magic")

        yield iterate(), counted.digest


def json_payload(data, limits):
    check("payload_bytes", len(data), limits)
    depth, quoted, escaped = 0, False, False
    for char in data:
        if quoted:
            if escaped:
                escaped = False
            elif char == 92:
                escaped = True
            elif char == 34:
                quoted = False
        elif char == 34:
            quoted = True
        elif char in (91, 123):
            depth += 1
            check("json_depth", depth, limits)
        elif char in (93, 125):
            depth -= 1
    return json.loads(data)


@contextmanager
def replay_json(replay, limits):
    """Validate the entire bounded serialization on disk before exposing output."""
    from .snapshots import snapshot_to_wire

    encoder = json.JSONEncoder(sort_keys=True, separators=(",", ":"), allow_nan=False)
    with tempfile.TemporaryFile(mode="w+b") as stream:
        size = 0

        def write(text):
            nonlocal size
            data = text.encode("utf-8")
            size += len(data)
            check("output_bytes", size, limits)
            stream.write(data)

        write('{"format":"livingproof-health/1","snapshots":[')
        for index, sample in enumerate(replay):
            if index:
                write(",")
            for part in encoder.iterencode(snapshot_to_wire(sample)):
                write(part)
        write("]}\n")
        stream.seek(0)
        yield stream
