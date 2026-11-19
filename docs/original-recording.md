# Original recorder evidence

This bounded slice follows [issue #1's handoff](https://github.com/Living-Proof-Labs/livingproof-health/issues/1#issuecomment-7008817719).
The fixture contains **original MCAP bytes emitted by the unchanged MuJoCo media
recorder**, paired with a newly generated simulation observation. It is separate
from the older `simulation-pose.mcap`, which remains an explicitly labeled
re-encoding of saved trace positions.

## Retrieval and generation

Retained GitHub artifact metadata was accessible. A candidate G1 corner recording
from verification run `43918093466`, artifact `14254230275`
(`unitree-g1-stock-mujoco-corner-mcap-stock`), was selected for inspection.
`gh run download` failed with `Forbidden` at GitHub's blob-storage endpoint.
No archive bytes were obtained, and no claim is made that the inaccessible
artifact matches the earlier G1 trial. No access controls were changed or bypassed.

The authorized fallback generated one G1 stock corner simulation using:

- MuJoCo producer **v3.2.1**, commit `f9c326f370cc3e54bf38932bfb332455dc4b5ef1`, and its unchanged development Dockerfile.
- G1 robot package **v2.2.1**, commit `68725986336c38d25a5ea421f895d9d796aed7f1`, and its committed `uv.lock`/model-policy checksum pins.
- The existing G1 corner lock's **content**, including stock profile, world and parameters, without changing the `0.5 m` fall threshold. The file was serialized with indentation, so its file hash differs from the older lock's formatting; the new evidence manifest records the new exact file hash.
- Linux amd64, Python 3.11.14, MuJoCo 3.17.0, NumPy 2.4.6, Torch 2.15.0+cpu, MCAP writer 1.6.0, uv 0.12.23. Full installed package identities are retained.

The normal `livingproof_sim_mujoco.evidence` command generated one trial. The
normal `livingproof_sim_mujoco.media` command then simulated it again, checked
that the resulting observation hash equaled the evidence hash, and only then
retained the MCAP and `media.json`. Its successful output was:

```text
1 MCAP recordings (214645 B), all matching their evidence
```

Video selection was empty, which suppresses videos while still recording every
trial's MCAP. No recorder, sampling, robot, validator, or threshold code was
modified. The original observation, evidence manifest, run manifest, media
manifest, MCAP, package inventory, and generation log are retained byte-for-byte
under [tests/fixtures/original-recording](../tests/fixtures/original-recording).
The [provenance manifest](../tests/fixtures/original-recording/provenance.json)
records checksums, source identities, image identity, and the retrieval failure.
These simulation outputs are Apache-2.0; no upstream model meshes, policy files,
or third-party source code are redistributed.

The new run is `walk-corner-unitree-g1-stock-20261119T122039Z`. Its observation
SHA-256 is `8337886b0509110df270dc34c6a78d6c3632dad46c05aac733f55a2e813f5424`,
**identical to the earlier saved G1 observation**. This establishes repeatability
for that observation in the tested environment; it does not retroactively turn
the older derived MCAP into original media. The new original MCAP checksum is
`0acbf1037b64f4b3aceaac6a1fcd83fd5b8599943a10c2815a8e09ac636bbef4`.

A second normal media invocation in a fresh Docker container passed the same
observation-hash check and produced **byte-identical MCAP** (`cmp` exit 0). Its
log is retained as `repeat.log`. This is an observed reproducibility result on
the stated platform, not a guarantee across hardware or dependency versions.

The producer emitted its existing TorchScript deprecation warning and its
wall-intrusion warning about using visual geometry for bodies without collision
geometry. Those warnings are preserved in the log. This slice assesses base pose,
not the accuracy of wall-intrusion or collision geometry.

## Assessment and interval evidence

The actual pinned scenario evaluator v1.3.8 assesses the original saved summary;
Health reads the actual MCAP. Neither result is copied or inferred from the other.

| Observation | Scenario summary | MCAP → Health |
| --- | --- | --- |
| Minimum base height | `0.7464 m` | `0.74637 m` |
| Occurrence time | `4.44 s` | `4440000000 ns` |
| Recorded scenario threshold | `0.5 m` | `0.5 m` |
| Height assessment | PASS | PASS, recorded samples only |

The minima differ by `0.00003 m`; the test explicitly preserves this numerical
disagreement. The threshold was not fitted to make them agree. Their PASS at the
recorded policy is not a guarantee of agreement at a precision-sensitive boundary.
Only the height check is compared, not an overall scenario success claim.

Both `/base_pose` and `/joint_states` have 614 messages. Pose log/publish timestamps
span `0` through `12260000000 ns`, with exactly `20000000 ns` between samples.
The saved observation ends `crossed_exit` at `12.26 s`, matching this recorded
interval. Payload timestamps and frame `world` are checked, as are the recorder's
quaternion fields. Health does not interpret joint state as hardware health.

As documented in the [producer gap analysis](parity-evidence.md), the producer's
observation and media paths are both nominally 50 Hz. The summary uses four
position decimals; MCAP uses five. Physics runs between these samples. A matching
recorded start/end and regular cadence do **not** prove the minimum between
samples, continuous-time behavior, or full-physics-step parity. No full-step
stream was captured, no sampling was changed, and there is no hardware evidence.
Keep #1 open and existing validators in place.

## Reproduce generation (Linux amd64, Docker)

From the Health repository, prepare fresh directories. These commands fetch the
released sources and checksum-pinned model/policy dependencies; no paid service
is needed. Generation is separate from ordinary Health tests and adds no simulator
or robot dependency to Health.

```sh
mkdir -p artifacts/original-reproduction

git clone --branch v3.2.1 https://github.com/Living-Proof-Labs/livingproof-sim-mujoco.git artifacts/producer-source
git clone --branch v2.2.1 https://github.com/Living-Proof-Labs/livingproof-unitree-g1.git artifacts/robot-source
# Verify these resolve to f9c326f370cc3e54bf38932bfb332455dc4b5ef1
# and 68725986336c38d25a5ea421f895d9d796aed7f1 respectively.
git -C artifacts/producer-source rev-parse HEAD
git -C artifacts/robot-source rev-parse HEAD

cp tests/fixtures/original-recording/corner.lock.json artifacts/original-reproduction/
cp tests/fixtures/original-recording/media-selection.json artifacts/original-reproduction/
cp tools/original-recording/generate.sh artifacts/original-reproduction/

docker build --target development -t health-mujoco-v3.2.1 artifacts/producer-source
docker run --rm --user "$(id -u):$(id -g)" -e MUJOCO_GL=osmesa \
  -v "$PWD/artifacts/robot-source:/robot" \
  -v "$PWD/artifacts/original-reproduction:/output" \
  -w /robot health-mujoco-v3.2.1 bash /output/generate.sh
```

To repeat only the normal recorder against the generated evidence, copy
`tools/original-recording/repeat.sh` to the same output directory and run the
same Docker invocation with `bash /output/repeat.sh`. It writes to `media-repeat`
and compares the MCAP bytes with `cmp`, preserving the first recording.

The executable script uses the robot's locked dependencies, then the unmodified
evidence/media commands. `media.json` must link the observation hash and MCAP
hash/size, and the media command must exit zero. Run IDs/manifest dates and timing
logs change on regeneration; do not claim identical manifest bytes. Check the
observation and MCAP bytes separately. CPU/platform differences can affect
simulation; any mismatch is evidence to report, never a reason to rewrite a hash.
The PR evidence records the managed environment's proxy/CA options and actual
image ID; ordinary Docker hosts do not need those environment-specific options.

## Offline fixture regression

After `task setup`, the four new tests run offline:

```sh
uv run --locked --no-sync --no-python-downloads pytest tests/test_original_recording.py -v
```

They check all retained file hashes, producer/robot identities, run and lock
linkage, original media pairing, channels/cadence/interval, actual evaluator and
Health results, their precision difference, and CLI replay/seek/assessment with
lossless wire timestamps. The existing suite verifies the evaluator's pinned
identity. Full Docker verification remains `task dev:verify`; hosted CI publishes
each case and retains JUnit reports for 30 days. CI uses the preserved real
recording and does not regenerate the simulation on every test run.
