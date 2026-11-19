#!/bin/bash
set -euo pipefail
uv sync --locked --no-default-groups --no-python-downloads
uv run --locked --no-sync --no-python-downloads python /health/tools/diagnostic-sidecar/collect.py
# Normal recorder independently enforces observation/MCAP pairing.
uv run --locked --no-sync --no-python-downloads python -m livingproof_sim_mujoco.media lpl_g1.adapter:ROBOT stock /health/tests/fixtures/original-recording/evidence /health/tests/fixtures/original-recording/media-selection.json /output/media
cmp /output/media/mcap/trial-01.mcap /health/tests/fixtures/original-recording/media/mcap/trial-01.mcap
