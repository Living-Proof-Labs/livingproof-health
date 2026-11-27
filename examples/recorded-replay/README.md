# Recorded replay → scenario comparison

This development example runs the **installed Health host plugin** on the retained
original G1 MCAP, then invokes the actual pinned scenario evaluator. It produces
portable JSON, a readable report and a local HTML viewer without an external
viewer, server or paid service.
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

- `viewer.html`: self-contained visual replay (see below).
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

## Portable visual replay

The offline Docker example emits **`viewer.html`**. This single file embeds the replay,
comparison, styles and JavaScript. It needs no ROS server, live topic stream,
external assets or paid viewer.

Serve the output directory on loopback, then open the viewer in your browser:

```sh
python3 -m http.server 8000 --bind 127.0.0.1 \
  --directory artifacts/replay-example/demo
```

Open <http://127.0.0.1:8000/viewer.html>. If your browser also permits opening
local files directly, File → Open is optional; it is not required.

Presentation semantics are deliberately separate from `Replay.seek`:

- The display selects the latest snapshot **at or before** the exact playhead.
  `Replay.seek` remains first at/after, unchanged.
- Duplicate timestamp ties use the **last snapshot in stable file order**.
  The slider and previous/next controls move between distinct recorded times;
  every duplicate remains inspectable in the full-snapshot section.
- Before the first timestamp, there is no observation. After the last, the last
  snapshot is displayed with an explicit age and after-last notice. Empty input
  is valid and disables sample controls. Time-only input shows “Not reported”.
- Between timestamps, the gap interval and exact observation age are visible.
  Missing fields are never copied from another snapshot, even across duplicates.
  There is no interpolation and no inference that old/absent evidence is healthy.
- The slider uses only bounded array indices. Enter arbitrary nonnegative decimal
  nanoseconds in **Exact playhead** and press Enter or Go to time. Lookup, playhead,
  observation timestamp and age use JavaScript `BigInt`; epoch times do not pass
  through `Number`. Arrow keys on the slider move between distinct timestamps.
- Optional height/frame/posture are conveniences. All arbitrary optional items and
  full duplicate snapshots remain inspectable as text. Scenario comparisons are
  in their own section and do not describe health at the playhead.

The HTML generator escapes raw-text script delimiters in embedded JSON. Robot
labels, values, frames and provenance are assigned via `textContent`, never HTML.
The artifact also declares a no-network content policy. Genuine fixture provenance
and recorded-sample limitations remain visible; synthetic browser fixtures are
explicitly labeled synthetic, not robot evidence.

### Verify the viewer

For a manual smoke test with the retained G1 recording, confirm there are
614 snapshots over 0–12.26 seconds. Seek to 4440000000 nanoseconds: the displayed
height should be 0.74637 m in frame `world`. Check keyboard stepping and the
layout on a narrow screen. The viewer itself should initiate no external requests.

Ordinary `task verify` checks exact lookup and safe embedding but does not
establish actual browser rendering. The retained optional Playwright checker
uses `file://` and is only for browsers that already permit it. The earlier
managed-browser refusal is retained as historical evidence, not a requirement
to change browser policy. Loopback static HTTP meets the portability requirement;
it serves the generated file, not a live data stream.

Independent loopback Chromium checks covered [synthetic interaction and safe text
rendering](https://github.com/Living-Proof-Labs/livingproof-health/pull/12#issuecomment-7057894281)
and the [retained genuine G1 recording](https://github.com/Living-Proof-Labs/livingproof-health/pull/12#issuecomment-7057966037).
The genuine check reused the verified artifact, inspected desktop and narrow-screen
renders, and observed no external or ROS requests. See the [evidence record](../../docs/evidence/visual-replay/status.json)
for exact scope. Issue #1 stays open for whole-trial parity. The viewer does not
replace validators or change the producer.

## Open existing evaluator details locally

The Health-owned template can open a published `livingproof-evaluator-health/1`
`health.json` without MCAP conversion or another simulation. This is a local
viewer demonstration, not a production report artifact or a scenario comparison.
Use the prepared development environment (`task setup`), then:

```sh
uv run --locked --no-sync python examples/recorded-replay/details.py health.json \
  --sha256 3ed6d7a52d2c071cfa8d93b873d6cd0912db20692dd66d0fc77e621018b83acb \
  --run-id walk-hallway-unitree-g1-stock-20261127T202136Z \
  --configuration stock --trial-index 1 --output health-viewer.html
```

For this example, download the original bytes from the
[existing G1 run's details](https://docs.livingprooflabs.com/verification-reports-action/reports/g1/unitree-g1/stock-mujoco-hallway/runs/46062882502/health.json).
Obtain the expected digest from a trusted evaluator result; computing a fresh hash
of arbitrary input is not provenance verification. The command checks the original
bytes and selects exactly one run/configuration/trial before writing any output.
It refuses missing snapshots, count mismatches, invalid timestamps, a wrong digest,
ambiguous trials, and an existing output file. The demo limits input to 16 MiB.
Explicit empty snapshots remain empty, and time-only observations remain time-only.

Open `health-viewer.html` locally in a browser. Enter `4440000000` in the exact
playhead field: this **574-sample** run records position
`(-0.46647, 0.0523, 0.74928)` m in `world`, with quaternion
`(x=0.005116, y=0.017098, z=0.023234, w=0.999571)`.
Its minimum recorded base height is `0.74814` m at `8460000000` ns.
These values differ from the older 614-sample fixture. The robot recording reports
no robot health telemetry; simulator poses do not fill that absence.
The viewer keeps its existing as-of playhead semantics, not interpolation or the
CLI's first-at-or-after seek semantics.

Trusted repository code renders JSON through the existing escaped data boundary
and text-only DOM operations; its CSP disallows network requests. The evaluator
supplies data, never HTML or JavaScript. The digest proves byte identity against
the supplied expectation, not the truth of the observations or hardware origin.
**Do not upload this generated demo to the reports origin.** A future trusted
static viewer and validated same-origin data link need a separate integration:
the current generic Reporter details link permits JSON/text, not a viewer URL.
No Action, Reporter, Verifier, contract, Pages, or publication changes are included.
This does not resolve #1's whole-trial parity work.
