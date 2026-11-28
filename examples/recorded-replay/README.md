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
Use the prepared development environment (`task setup`). The published report
history can be reset, so begin at the
[stable G1 latest report](https://docs.livingprooflabs.com/verification-reports-action/reports/g1/unitree-g1/stock-mujoco-hallway/latest/)
each time; do not bookmark a particular run's data URL.

1. Follow **Latest report** if the page does not redirect automatically. In that
   report's **Health** card, open **Recorded data** and save the original file as
   `health.json` in your working directory. Do not copy/paste or reformat its JSON.
2. On the **same run's report page**, expand **Full lossless report**. Find
   `advisory_results`, then `livingproof-health` → `advisory` → `details_file`.
   Confirm its `uri` is `health.json` and copy its complete `sha256` value.
   Do not use a descriptor, MCAP, or another run's checksum. If Health, Recorded
   data, or this checksum is absent, stop: that report cannot supply this example.
3. Replace the placeholder below with that report-published checksum. Verify the
   downloaded bytes **before** reading their run/configuration/trial identity:

```sh
export REPORT_SHA256='<64-character checksum copied from the same report>'
python - <<'PYTHON'
import hashlib
import json
import os
from pathlib import Path

raw = Path("health.json").read_bytes()
if hashlib.sha256(raw).hexdigest() != os.environ["REPORT_SHA256"]:
    raise SystemExit("Checksum mismatch: return to the same report and download again")
for item in json.loads(raw)["trials"]:
    print(json.dumps(item["trial"], sort_keys=True))
PYTHON
```

Computing a hash of arbitrary input and using that as the expected checksum is
not provenance verification. The expected value must come from the report.
If the history disappears during download, restart from latest; never mix a
previous report's checksum with new data.

4. Choose one printed trial. Replace the three placeholders below with its exact
   `run_id`, `configuration`, and integer `index`. Keep the same verified file and
   checksum. Choose a new output filename if `health-viewer.html` already exists.

```sh
uv run --locked --no-sync python examples/recorded-replay/details.py health.json \
  --sha256 "$REPORT_SHA256" \
  --run-id '<run_id from the verified file>' \
  --configuration '<configuration from that same trial>' \
  --trial-index '<integer index from that same trial>' --output health-viewer.html
```

The command checks the original bytes again and selects exactly one trial before
writing output. It refuses missing snapshots, count mismatches, invalid timestamps,
a wrong digest, ambiguous trials, and an existing output file. The demo limits
input to 16 MiB. Explicit empty snapshots remain empty, and time-only observations
remain time-only.

Open `health-viewer.html` locally in a browser. Select a recorded time on the
slider or enter its `time_ns` in the exact playhead field. Compare the displayed
values with that snapshot in your verified file; sample counts, poses and times
vary by run. Simulator poses do not fill absent robot telemetry. The viewer keeps
its existing as-of playhead semantics, not interpolation or the CLI's
first-at-or-after seek semantics.

Trusted repository code renders JSON through the existing escaped data boundary
and text-only DOM operations; its CSP disallows network requests. The evaluator
supplies data, never HTML or JavaScript. The digest proves byte identity against
the supplied expectation, not the truth of the observations or hardware origin.
**Do not upload this generated demo to the reports origin.** A future trusted
static viewer and validated same-origin data link need a separate integration:
the current generic Reporter details link permits JSON/text, not a viewer URL.
No Action, Reporter, Verifier, contract, Pages, or publication changes are included.
This does not resolve #1's whole-trial parity work.

## One-click local card preview

This development preview adds a clickable **Health** card in front of the same
replay controls. It is clearly labelled as a local G1 card preview, not a real
production report. It does not change grading or any published report.

First follow **Open existing evaluator details locally** above to save unchanged
`health.json`, verify it against the **same report's published checksum**, and
print its trial identities. In that prepared development environment, replace
these placeholders with the selected trial's values:

```sh
uv run --locked --no-sync python examples/recorded-replay/preview.py health.json \
  --sha256 "$REPORT_SHA256" \
  --run-id '<run_id from the verified file>' \
  --configuration '<configuration from that same trial>' \
  --trial-index '<integer index from that same trial>' --output health-preview
python3 -m http.server 8000 --bind 127.0.0.1 --directory health-preview
```

Open <http://127.0.0.1:8000/> and click **Open replay**. The link selects that exact
run/configuration/trial. Use the slider, previous/next buttons, or exact time field
(Enter submits) to inspect recorded snapshots. Sample values come from the input,
not a fixed pose expectation. Stop the server with Ctrl+C. Choose a new output
directory to build another preview; existing previews are never overwritten.

The builder reuses the local CLI's validation and copies original JSON bytes.
The trusted static viewer contains no run data or evaluator-supplied executable
content. At click time it fetches only `data/<name>.json` beside the viewer, without
credentials or redirects, with a 15-second timeout and a 16 MiB limit. It verifies
SHA-256 **before parsing**, then checks the selected trial, sample count and
snapshot timestamps. Invalid/missing data gives an error instead of observations.
Empty and time-only recordings are allowed. Robot telemetry stays separate from
simulator observations; missing telemetry is never a healthy verdict.

The checksum and trial in a link are expectations, not a signature: a party who
can rewrite both the link and data can rewrite the preview. Use only expectations
from the trusted source report. Arbitrary query strings, remote origins, path
traversal and executable data links are not supported. JavaScript and HTTP on
loopback are required; opening `viewer.html` directly as a file is not supported.

**Keep this preview local.** Production integration needs a separately approved
generic viewer-link capability and versioned Health hosting. This slice does not
widen Reporter's data-link contract or publish HTML through evaluator artifacts.
Related work: #1 (broader Health observations) and #5 (manual/hosting); neither is
completed by this preview.

For review, `task verify` includes Node tests for the loader and a Python test of
the actual preview command. In a prepared browser-test environment with Playwright
and `/usr/bin/chromium`, keep the preview server running and execute:

```sh
node tools/review/static_preview_browser.cjs health-preview http://127.0.0.1:8000/
```

That optional probe uses the existing G1 recording with a sample at 4.44 seconds,
compares the displayed pose directly with those JSON bytes, tests Enter and arrow
keys at 360/390/430 px, and checks stale-data refusal, missing data and a labelled
synthetic time-only case. Screenshots stay inside the local preview directory.
It is not a simulation or a requirement to install browser tooling on shared hosts.
