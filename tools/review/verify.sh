#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail
# Fail before pytest collection, dependency execution or fixture generation.
python -c 'from tools.review.zstd_probes import containment; print(containment())'
export UV_OFFLINE=1 LIVINGPROOF_WHEEL_DIR=/tmp/health-wheels HEALTH_BOUNDED_TESTS=1
unset LIVINGPROOF_NETWORK
task setup
task verify
uv run --locked --no-sync python tools/review/zstd_probes.py 2>&1 | tee artifacts/review-zstd-command.log
