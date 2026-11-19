#!/bin/bash
set -euo pipefail
uv sync --locked --no-default-groups --no-python-downloads
uv run --locked --no-sync --no-python-downloads python -m livingproof_sim_mujoco.evidence lpl_g1.adapter:ROBOT stock /output/evidence --lock /output/corner.lock.json --trials 1
uv run --locked --no-sync --no-python-downloads python -m livingproof_sim_mujoco.media lpl_g1.adapter:ROBOT stock /output/evidence /output/media-selection.json /output/media
uv pip freeze --python /opt/mujoco-venv/bin/python > /output/installed-packages.txt
