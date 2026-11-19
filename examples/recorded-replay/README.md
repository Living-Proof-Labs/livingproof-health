# Recorded replay → scenario comparison

This development example runs the **installed Health host plugin** on the retained
original G1 MCAP, then invokes the actual pinned scenario evaluator. It produces
portable JSON and a readable report without a viewer, server or paid service.
It is a Health integration example, not the general scenario binding runner.

## Prepare once, run offline

From the repository root, build the development example image. This setup may
fetch dependencies pinned in `uv.lock` (including host CLI v1.5.4 and scenario
evaluator v1.3.8). The evaluator and host are development dependencies only.
Health is installed non-editably in the image; commands discover its installed
entry point. No source-tree import override is used.

```sh
docker build --target replay-example -t health-replay-example .
mkdir -p artifacts/replay-example
```

Then this **one Docker command** runs the prepared demonstration offline and
prints the report. Use a new output directory on each run; an existing report
is never silently reused or overwritten.

```sh
docker run --rm --network none --user "$(id -u):$(id -g)" \
  -v "$PWD/artifacts/replay-example:/output" health-replay-example
```

Open `artifacts/replay-example/demo/comparison.md`. The adjacent files are:

- `replay.json`: portable Health snapshots; nanosecond timestamps are strings.
- `comparison.json`: input SHA-256, paired observation hash/run identity,
  expectation, frame, interval, measured sampling, each separate result and limits.
- `replay-summary.json`: explicit example-only minimum-summary bridge.
- `seek-4440000000.json`, `seek-4440000001.json`, `seek-12260000001.json`:
  exact installed-command outputs, including `null` beyond the source interval.

The genuine input SHA-256 is
`0acbf1037b64f4b3aceaac6a1fcd83fd5b8599943a10c2815a8e09ac636bbef4`.
Its [original recorder provenance](../../docs/original-recording.md) includes the
producer/G1 pins, original bytes and manifest pairing. The example checks the
MCAP and original observation hashes against the producer's media manifest.

Expected default comparison, explicit minimum **0.5 m** in frame **world**:

| Path | Result | Minimum | Occurrence |
| --- | --- | --- | --- |
| Installed Health assessment | PASS | 0.74637 m | 4440000000 ns |
| Actual evaluator, replay-derived summary | PASS | 0.74637 m | 4.44 s |
| Actual evaluator, original saved summary | PASS | 0.7464 m | 4.44 s |

There are 614 snapshots, from 0 to 12260000000 ns, spaced 20000000 ns apart
(50 Hz). The original summary and replay differ in precision; neither replaces
the other. At `--minimum-m 0.74637`, equality passes both paths. At
`--minimum-m 0.74638`, Health and the replay-summary evaluator FAIL while the
rounded original-summary evaluator still PASSes. Try that case offline:

```sh
docker run --rm --network none --user "$(id -u):$(id -g)" \
  -v "$PWD/artifacts/replay-example:/output" health-replay-example \
  --output /output/boundary --minimum-m 0.74638 --frame-id world
```

A completed comparison exits zero even when a path reports FAIL: this command
produces an example report, not a production grade. A malformed input, missing
command, invalid output or mismatched command exit/result fails nonzero and
publishes no new report. A nonempty/existing output path is rejected.

## Exact seek commands

The demonstration invokes these installed commands internally:

```sh
livingproof capability health replay trial-01.mcap
livingproof capability health seek replay.json --time-ns 4440000000
livingproof capability health seek replay.json --time-ns 4440000001
livingproof capability health seek replay.json --time-ns 12260000001
livingproof capability health assess replay.json --minimum-m 0.5 --frame-id world
```

To inspect the exported replay yourself with the prepared image:

```sh
docker run --rm --network none --entrypoint livingproof \
  -v "$PWD/artifacts/replay-example:/output:ro" health-replay-example \
  capability health seek /output/demo/replay.json --time-ns 4440000000
```

The exact-time output has `"time_ns": "4440000000"` and base-pose position
`"z": 0.74637` (plus frame, source hash, orientation and other position fields).
Changing the requested time to `4440000001` returns `"time_ns": "4460000000"`.
Requesting `12260000001` returns exactly `null`. Seek returns the first snapshot
at or after the requested time, with no interpolation or carried-forward data.
The saved seek files contain the full expected output.

## Boundaries and bridge

Time remains the only universal Health requirement. This example's **explicit**
scenario expectation requires a reported base height in the selected frame.
The Health assessment traverses all recorded samples. The bridge passes its
minimum/time to the real `hallway-fall` evaluator only when evidence is complete;
missing required posture, wrong frame or insufficient time coverage gives the
evaluator an empty observation, so its own missing-evidence behavior runs.
No evaluator verdict rule is copied. A known violation with some missing data
can therefore produce Health FAIL and evaluator INSUFFICIENT_EVIDENCE; the report
preserves both. The saved original summary is compared only for the genuine
fixture in its world frame. Other inputs are explicitly unauthenticated.

For time-only portable JSON, use `--portable-json --input /output/input.json`.
For another supported MCAP, use `--input /output/trial.mcap`. These are development
inputs, not a generalized robot binding facility. Other evaluator parameters
remain the example's frozen corner configuration.

**No whole-trial parity:** original recording/summary sampling and rounding can
miss brief changes; raw producer positions have a measured 2 ms freshness lag;
terminal coverage also has documented limits. See the
[diagnostic evidence](../../docs/diagnostic-sidecar.md) and
[time-limit evidence](../../docs/time-limit-evidence.md). This slice adds no
producer experiment or fix. All results are simulation/recorded-sample evidence,
not hardware health or safety certification. No production evaluator-result or
overall scenario grade is emitted. Issue #1 remains open and validators stay in place.

Normal `task verify` tests the real installed host commands and evaluator, including
threshold equality/disagreement, missing posture, malformed input and command
failures. Existing tests retain epoch-nanosecond, brief-dip and single-instant
coverage. The image build excludes `.git`, so its Health version may use the
source-archive fallback; independent-review evidence identifies the exact commit
and resulting image digest. The development image is built locally, not published.
