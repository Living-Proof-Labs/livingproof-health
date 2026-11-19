#!/bin/bash
set -euo pipefail
uv sync --locked --no-default-groups --no-python-downloads
uv run --locked --no-sync --no-python-downloads python /health/tools/time-limit/collect.py
