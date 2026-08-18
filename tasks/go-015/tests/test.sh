#!/bin/bash
# Harbor verifier entrypoint. Delegates to run_tests.py.
set -euo pipefail

LOG_DIR="${HARBOR_LOG_DIR:-/logs/verifier}"
mkdir -p "$LOG_DIR"

chmod +x /tests/parse 2>/dev/null || true
chmod +x /tests/run_tests.py 2>/dev/null || true

python3 /tests/run_tests.py --config /tests/config.json --log-dir "$LOG_DIR"
