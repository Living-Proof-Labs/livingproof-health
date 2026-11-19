#!/bin/bash
set -euo pipefail
uv sync --locked --no-default-groups --no-python-downloads
uv run --locked --no-sync --no-python-downloads python -m livingproof_sim_mujoco.media lpl_g1.adapter:ROBOT stock /output/evidence /output/media-selection.json /output/media-repeat
cmp /output/media/mcap/trial-01.mcap /output/media-repeat/mcap/trial-01.mcap
