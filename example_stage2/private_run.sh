#!/usr/bin/env bash
set -Eeuo pipefail

N_CONCURRENT=10

fail() {
    echo "ERROR: $*" >&2
    exit 1
}

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
CONFIG_FILE="${SCRIPT_DIR}/submission.yaml"
PYTHON_BIN="${PROJECT_DIR}/.venv/bin/python"

[[ -f "$CONFIG_FILE" ]] || fail "submission.yaml is missing"
[[ -x "$PYTHON_BIN" ]] || fail "Python environment is missing: $PYTHON_BIN"

USERNAME="$("$PYTHON_BIN" - "$CONFIG_FILE" <<'PY'
import re
import sys
from pathlib import Path

import yaml

data = yaml.safe_load(Path(sys.argv[1]).read_text(encoding="utf-8"))
username = data.get("username") if isinstance(data, dict) else None
if not isinstance(username, str) or not re.fullmatch(
    r"[a-z0-9][a-z0-9_.-]{0,63}", username
):
    raise SystemExit("submission.yaml contains no valid username")
print(username)
PY
)"

IMAGE_NAME="inference_image_${USERNAME}"
CONTAINER_NAME="inference_container_${USERNAME}"

cleanup() {
    echo "Cleaning up $CONTAINER_NAME and $IMAGE_NAME"
    docker container rm --force "$CONTAINER_NAME" >/dev/null 2>&1 || true
    docker image rm --force "$IMAGE_NAME" >/dev/null 2>&1 || true
}

trap cleanup EXIT

# Remove leftovers from an interrupted previous run of this submission only.
cleanup

export SWE_MERA_TASKS_DIR="${SWE_MERA_TASKS_DIR:-${PROJECT_DIR}/tasks}"
export SWE_MERA_JOBS_DIR="${SWE_MERA_JOBS_DIR:-${PROJECT_DIR}/jobs/stage2/${USERNAME}}"
export SWE_MERA_N_CONCURRENT="${SWE_MERA_N_CONCURRENT:-$N_CONCURRENT}"

"${SCRIPT_DIR}/run.sh"
