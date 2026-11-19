#!/bin/bash
# Run from the Health checkout; image and robot checkout pins are documented.
set -euo pipefail
output="${1:?output directory required}"
mkdir -p "$output"
output="$(realpath "$output")"
DOCKER_CONFIG=/tmp/health-docker docker run --rm --network host --user "$(id -u):$(id -g)" \
  -e HTTP_PROXY -e HTTPS_PROXY -e NO_PROXY -e http_proxy -e https_proxy -e no_proxy \
  -e SSL_CERT_FILE=/run/ca.pem -e GIT_SSL_CAINFO=/run/ca.pem -e UV_SYSTEM_CERTS=true \
  -e MUJOCO_GL=osmesa -v /etc/ssl/certs/ca-certificates.crt:/run/ca.pem:ro \
  -v /workspace/health-g1-producer:/robot -v "$PWD:/health:ro" -v "$output:/output" \
  -w /robot health-mujoco-v3.2.1 bash /health/tools/diagnostic-sidecar/run.sh
