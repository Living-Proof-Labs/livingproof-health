#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Run only in the constrained preparation container; never generate fixtures here.
set -euo pipefail
python -c 'from tools.review.zstd_probes import containment; print(containment(offline=False))'
task setup
mkdir -p /tmp/health-wheels
curl --fail --location --max-time 60 --output /tmp/health-wheels/livingproof-1.5.4-py3-none-any.whl \
  https://github.com/Living-Proof-Labs/livingproof/releases/download/v1.5.4/livingproof-1.5.4-py3-none-any.whl
curl --fail --location --max-time 60 --output /tmp/health-wheels/livingproof_common-1.0.0-py3-none-any.whl \
  https://github.com/Living-Proof-Labs/livingproof-common/releases/download/v1.0.0/livingproof_common-1.0.0-py3-none-any.whl
echo 'f01fa04a78254047a2c062478556107d036be18af98f3f8a3ddb5b0d11266639  /tmp/health-wheels/livingproof-1.5.4-py3-none-any.whl
8b7795748b54eeb89610f3716245f45db48ac0474465a5abbf974e7075c1476c  /tmp/health-wheels/livingproof_common-1.0.0-py3-none-any.whl' | sha256sum --check
# Prime build and installation caches without invoking the installed application.
uv build --offline --wheel --out-dir /tmp/health-build
uv venv --python /usr/local/bin/python --no-python-downloads /tmp/health-install
uv pip install --python /tmp/health-install/bin/python /tmp/health-wheels/*.whl /tmp/health-build/*.whl
