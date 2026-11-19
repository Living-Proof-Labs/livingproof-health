# Bounded MCAP replay input

Issue [#13](https://github.com/Living-Proof-Labs/livingproof-health/issues/13) concerns
a source-verified resource-bounds gap, **not a reproduced Health exploit or incident**.
A caller-selected MCAP is untrusted input. Accepted recordings retain the same
snapshot contract, stable ordering, integer times, provenance digest and canonical
JSON bytes. The genuine G1 fixture's replay SHA-256 remains
`90d8ccc2df0a3c8a81aaea0efcf5af90c3112d4945be95fe6e37a6a742dab77c`.
There is no sampling, truncation or invented observation on exhaustion.

## Policy and configuration

The defaults accommodate the retained 614-snapshot original recording with substantial
headroom. They deliberately bound this in-memory observation API, rather than
promise to hold an arbitrarily long recording. At roughly 500 serialized bytes
per snapshot, the 8 MiB retention budget holds about five minutes at 50 Hz; actual
capacity depends on fields/provenance. Larger useful recordings can explicitly
raise relevant limits, within hard ceilings, or be processed separately by their
producer without silently decimating them here.

| JSON / Python limit | Default | What is counted |
| --- | ---: | --- |
| `input_bytes` | 128 MiB | Actual original file bytes, including unselected data, indexes and summary |
| `compressed_chunk_bytes` | 8 MiB | One chunk's compressed data (record framing permits at most 44 extra header bytes) |
| `expanded_chunk_bytes` | 8 MiB | Declared **and actual** bytes of one chunk |
| `decoder_window_bytes` | 8 MiB | zstd frame window, independent of output budget |
| `expanded_total_bytes` | 128 MiB | Cumulative actual expanded bytes, all chunks |
| `record_bytes` | 4 MiB | Body of each non-chunk record, including nested/unknown/unselected records |
| `payload_bytes` | 256 KiB | Every message payload, selected or not |
| `records` | 250,000 | Outer and inner record headers, including summary/index records |
| `chunks` | 1,000 | Every chunk, selected or not |
| `metadata_bytes` | 8 MiB | Cumulative schema/channel body bytes, including repeated summary definitions |
| `snapshots` | 20,000 | Selected snapshots retained |
| `retained_bytes` | 8 MiB | Canonical serialized selected snapshots, including full provenance |
| `output_bytes` | 32 MiB | Exact UTF-8 canonical output, framing and newline included |
| `json_depth` | 64 | Selected JSON payload nesting before decoding |

A limit includes equality; exceeding it rejects the whole replay. Integer overrides
must be positive (booleans are rejected), at most **eight times the default**;
JSON depth has a hard ceiling of 128. Unknown keys, oversized configuration files
(over 4096 bytes) and non-finite/non-integer values are errors. Configuration is an
operator policy, not something read from recording metadata.

```json
{"snapshots":40000,"retained_bytes":16777216,"output_bytes":67108864}
```

```sh
livingproof capability health replay trial.mcap --limits limits.json --output replay.json
# Python callers use read_mcap(path, limits=Limits(...)).
```

Defaults require no options. Errors name the violated budget and exit nonzero.
The input must be a regular local file, not a FIFO/device; it is opened without
blocking on a pipe on POSIX. Other operating systems are not part of the measured
resource-containment evidence. Size is checked before reading, **and actual reads are counted**
so a changing file cannot evade that limit. SHA-256 is updated during this same
single pass; no whole-file `read_bytes()` allocation or second source read occurs.

## Allocation, decoding and output boundary

The directly used native codec APIs are pinned to **zstandard 0.25.0 / lz4 4.4.5**
(the same versions previously in the development lock); other codec versions are
not covered by this resource contract. Health retains the pinned MCAP **1.3.0** `StreamReader` and its schema/channel/message
field decoders. A small framing guard caps each body before reading it and keeps
internal field lengths inside that record. A narrow subclass wraps the pinned
`_read_record` hook to distinguish body reads from next-record reads; no upstream
field decoder is copied. This private hook is an explicit compatibility constraint
and requires regression review with any MCAP upgrade.

Chunks are emitted by the upstream reader without its unbounded decompression
path. Native zstd/lz4 streaming calls return at most a 64 KiB block (or the remaining
budget plus one detection byte). Health checks frame declarations/window and actual
output, total expansion, exact declared-versus-actual length and chunk CRC before
feeding inner records through the same guarded upstream decoder. Inner iteration
uses a synthetic footer only to terminate the upstream iterator; it is not evidence
and is neither emitted nor counted. Nested chunks/other MCAP structural records
inside chunks are invalid; unknown extension records still consume budgets.

For zstd, a second **bounded** single-frame decode verifies completion/trailing data:
stream-reader EOF alone can accept truncated input. This uses at most the already
capped output room and rejects extra frames/data. The locked backend passes
`max_window_size` directly to `ZSTD_DCtx_setMaxWindowSize` in bytes; we also inspect
frame `window_size` before decoder creation rather than relying on an ambiguous
unit description. lz4 verifies end-of-frame and rejects unused/truncated data;
its frame block size has the codec's 4 MiB maximum. Supported compression names are
empty, `zstd` and `lz4`; unknown codecs, external dictionaries and concatenated
multi-frame chunk encodings are not promised. Codec errors reject input, never fall
back to treating compressed bytes as raw records.

All physical records are visited, regardless of topic or summary indexes. Upstream
data-section CRC checking and closing magic remain enabled; chunk CRC checks are
performed on the bounded actual expansion. Conflicting schema/channel IDs are
rejected. Selected messages still require the same PoseInFrame JSON encoding.
This path does not weaken schema checks or depend on an untrusted index to decide
which chunks need budget checks. It may reject malformed or unsupported files
previously tolerated by the seeking reader; it does not silently omit their data.

Retention and output are independently metered. Output includes JSON escaping,
repeated provenance and container overhead; compressed file size alone is not an
output bound. `read_mcap` validates canonical serialization before returning its
Replay. The CLI serializes to a capped temporary file, then publishes it only after
all validation completes. `--output` uses a sibling temporary and atomic replacement;
validation, budget and publication errors clean up temporaries and leave an existing
result intact. Temporary disk usage is bounded by the output budget.

Default stdout stays byte-compatible. Validation/budget failures produce **zero JSON
stdout**, including late corruption. Once a validated stream is being written to
stdout, a broken pipe or destination I/O failure cannot be rolled back; use `--output`
for an atomic file, and always honor the CLI exit status. A shell's `> replay.json`
can itself create/truncate a file before the CLI starts, which Health cannot undo.

These are byte/count/depth budgets, **not exact RSS or elapsed-time guarantees**.
Python objects, copies required by the existing Replay API, escaping, codec workspaces
and temporary buffers amplify memory beyond serialized sizes. Raising limits requires
appropriate process/disk ceilings. Slow storage and native codec defects are not
eliminated. Portable JSON `seek`/`assess` input and arbitrary in-memory Replay creation
are separate boundaries; this change does not claim to bound them.

## Reuse decision and proposed shared boundary

Inspected evaluator-run at commit
[`54f7636e17b8bafa84f1c90daa9ebd05ef379698`](https://github.com/Living-Proof-Labs/livingproof-evaluator-run/blob/54f7636e17b8bafa84f1c90daa9ebd05ef379698/src/livingproof_evaluator_run/mcap_reader.py)
(reader blob `18b4aec248e1570aae8baeac5a7828ab36211680`). Its public messages are
**topic/log-time only**, using MCAP 1.6.0; Health needs schema definitions, encoding,
message bytes, sequence, publish time and original-byte hashing, using pinned 1.3.0.
Its completeness/summary/channel-statistics result is also different from Health's
optional-observation replay and canonical JSON output.

Shared invariants: untrusted chunk declarations, actual expansion caps, CRCs,
file-order preservation and explicit rejection on exhausted limits. Its current
preflight reads compressed chunk data before checking expansion, and opens/parses
summary data before that preflight; it does not supply Health's compressed-input,
payload, retention or serialized-output budgets. It therefore is not a safe drop-in
for this boundary, and its parser/guard was **not copied** here.

Proposal for Rivet/Keel coordination: a shared bounded **record iterator** with
original-byte digest, schema/channel/message payload access, deterministic physical
order, pre-read framing, compressed/actual expansion/window caps and CRC validation.
Consumers would retain their own observation/result semantics, selected retention
and output policies. This requires an agreed public API and dependency/version
alignment; no cross-repository edits or unilateral API expansion are included.
Visual PR #12 is separate, untouched and still blocked on real-browser evidence.

## Safely bounded verification

Do not run adversarial fixtures directly on a host. `task dev:verify` and hosted
CI build/use the development Docker image with **512 MiB memory and swap ceiling,
2 CPUs, 128 PIDs, and 300-second suite timeout**. Each small adversarial case runs
in a separate child with **256 MiB address space, 8 CPU seconds and 12 wall seconds**.
The child checks Docker and its actual cgroup ceiling before generating fixtures.
The worker records Linux `getrusage` peak RSS, current-program `/proc` `VmHWM`,
and case elapsed time under `artifacts/bounds/*.json`; the parent adds full child
wall time including startup. Peaks are observed high-water marks, not allocation
deltas, and the process-launch high-water mark can dominate `getrusage`.
hosted JUnit artifacts retain these alongside individual test results.

Cases use only small inputs: zstd/lz4 actual expansion, false declarations,
truncation, unselected chunks/messages, many small records, huge length fields
without huge data, payload/retention/output limits, near-limit success, Unicode
output amplification, late CRC failure, failed atomic replacement and compatibility.
No unbounded exhaustion is attempted. Existing genuine replay, optional/time-only,
threshold, lossless timestamp and seek tests remain in the full suite.

```sh
task dev:verify
# Cases and measurements are in tools/bounds/case.py and tests/test_recording_bounds.py.
```
