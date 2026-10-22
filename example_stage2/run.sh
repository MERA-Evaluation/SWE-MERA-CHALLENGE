#!/usr/bin/env bash
set -Eeuo pipefail

# Fixed evaluation settings. They are intentionally not read from submission.yaml.
GPU_COUNT=3
BUILD_TIMEOUT_SEC=21600
STARTUP_TIMEOUT_SEC=1800
AGENT_TIMEOUT_MULTIPLIER=1
DOCKER_GATEWAY="${SWE_MERA_DOCKER_GATEWAY:-127.0.0.1}"
MODEL_PORT="${SWE_MERA_MODEL_PORT:-8000}"
MODEL_API_KEY="dummy"

fail() {
    echo "ERROR: $*" >&2
    exit 1
}

usage() {
    cat <<'HELP'
Usage: run.sh --username NAME

Build and run a Stage 2 submission, then remove its container and image.
NAME identifies Docker resources and the default job directory; it is not
read from submission.yaml. Use 1-64 lowercase letters, digits, '.', '_' or
'-', starting with a letter or digit.

Optional environment variables:
  SWE_MERA_TASKS_DIR       Task directory (default: <project>/tasks)
  SWE_MERA_JOBS_DIR        Output directory (default: <project>/jobs/stage2/NAME)
  SWE_MERA_N_CONCURRENT    Concurrent tasks (default: 10)
  SWE_MERA_DOCKER_GATEWAY  API bind address (default: 127.0.0.1)
  SWE_MERA_MODEL_PORT      API port (default: 8000)
HELP
}

USERNAME=""
while (($#)); do
    case "$1" in
        --username)
            [[ $# -ge 2 && -n "$2" && "$2" != --* ]] || fail \
                "--username requires a value"
            [[ -z "$USERNAME" ]] || fail "--username may only be supplied once"
            USERNAME="$2"
            shift 2
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        *)
            fail "unknown argument: $1 (use --help)"
            ;;
    esac
done
[[ -n "$USERNAME" ]] || fail "--username is required (use --help)"
[[ "$USERNAME" =~ ^[a-z0-9][a-z0-9_.-]{0,63}$ ]] || fail \
    "--username must be 1-64 lowercase letters, digits, '.', '_' or '-', starting with a letter or digit"

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
CONFIG_FILE="${SCRIPT_DIR}/submission.yaml"
PYTHON_BIN="${PROJECT_DIR}/.venv/bin/python"
HARBOR_BIN="${PROJECT_DIR}/.venv/bin/harbor"

[[ -f "$CONFIG_FILE" ]] || fail "submission.yaml is missing"
[[ -x "$PYTHON_BIN" ]] || fail "Python environment is missing: $PYTHON_BIN"
[[ -x "$HARBOR_BIN" ]] || fail "Harbor is missing: $HARBOR_BIN"
[[ -f "${SCRIPT_DIR}/inference/Dockerfile" ]] || fail \
    "inference/Dockerfile is missing"
[[ -x "${SCRIPT_DIR}/inference/test.sh" ]] || fail \
    "inference/test.sh is missing or not executable"
TIMEOUT_BIN="$(command -v timeout || command -v gtimeout || true)"
[[ -n "$TIMEOUT_BIN" ]] || fail "GNU timeout is required (timeout or gtimeout)"

CONFIG="$("$PYTHON_BIN" - "$CONFIG_FILE" <<'PY'
import re
import sys
from pathlib import Path

import yaml

path = Path(sys.argv[1])
data = yaml.safe_load(path.read_text(encoding="utf-8"))

if not isinstance(data, dict):
    raise SystemExit("submission.yaml must contain a YAML object")

allowed = {"agent", "model"}
unknown = sorted(set(data) - allowed)
if unknown:
    raise SystemExit(f"unknown submission fields: {', '.join(unknown)}")

agent = data.get("agent")
if agent not in {"mini_swe_agent", "custom_agent"}:
    raise SystemExit("agent must be 'mini_swe_agent' or 'custom_agent'")

model = data.get("model")
if not isinstance(model, str) or not re.fullmatch(
    r"[A-Za-z0-9][A-Za-z0-9._/-]{0,127}", model
):
    raise SystemExit("model is required and contains unsupported characters")

print(agent, model, sep="\t")
PY
)"

IFS=$'\t' read -r AGENT_KIND MODEL_NAME <<<"$CONFIG"

IMAGE_NAME="inference_image_${USERNAME}"
CONTAINER_NAME="inference_container_${USERNAME}"
MODEL_BASE_URL="http://${DOCKER_GATEWAY}:${MODEL_PORT}/v1"

case "$AGENT_KIND" in
    mini_swe_agent)
        HARBOR_AGENT="mini-swe-agent"
        ;;
    custom_agent)
        [[ -f "${SCRIPT_DIR}/custom_agent/react_bash_agent.py" ]] || fail \
            "custom_agent/react_bash_agent.py is missing"
        HARBOR_AGENT="custom_agent.react_bash_agent:ReactBashAgent"
        ;;
    *)
        fail "unsupported agent: $AGENT_KIND"
        ;;
esac

SWE_MERA_TASKS_DIR="${SWE_MERA_TASKS_DIR:-${PROJECT_DIR}/tasks}"
SWE_MERA_JOBS_DIR="${SWE_MERA_JOBS_DIR:-${PROJECT_DIR}/jobs/stage2/${USERNAME}}"
[[ -d "$SWE_MERA_TASKS_DIR" ]] || fail "task directory is missing: $SWE_MERA_TASKS_DIR"

N_CONCURRENT="${SWE_MERA_N_CONCURRENT:-10}"
[[ "$N_CONCURRENT" =~ ^[1-9][0-9]*$ ]] || fail \
    "SWE_MERA_N_CONCURRENT must be a positive integer"

cleanup() {
    echo "Cleaning up $CONTAINER_NAME and $IMAGE_NAME"
    docker container rm --force "$CONTAINER_NAME" >/dev/null 2>&1 || true
    docker image rm --force "$IMAGE_NAME" >/dev/null 2>&1 || true
}

finish() {
    local status=$?
    trap - EXIT
    cleanup
    exit "$status"
}

trap finish EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
# Remove leftovers belonging to this username before starting a new run.
cleanup

echo "STAGE2_PHASE=build"
echo "Building $IMAGE_NAME (timeout: ${BUILD_TIMEOUT_SEC}s)"
if "$TIMEOUT_BIN" --signal=TERM --kill-after=60s "${BUILD_TIMEOUT_SEC}s" \
    docker build --tag "$IMAGE_NAME" "${SCRIPT_DIR}/inference"; then
    :
else
    build_status=$?
    if [[ "$build_status" -eq 124 ]]; then
        echo "ERROR: Docker build timed out after ${BUILD_TIMEOUT_SEC}s" >&2
    else
        echo "ERROR: Docker build failed with exit code ${build_status}" >&2
    fi
    exit "$build_status"
fi

echo "STAGE2_PHASE=start"
echo "Starting $CONTAINER_NAME with $GPU_COUNT GPU(s)"
docker run \
    --detach \
    --name "$CONTAINER_NAME" \
    --gpus "$GPU_COUNT" \
    --ipc host \
    --ulimit memlock=-1:-1 \
    --ulimit stack=67108864:67108864 \
    --publish "${DOCKER_GATEWAY}:${MODEL_PORT}:8000" \
    "$IMAGE_NAME"

echo "STAGE2_PHASE=model_check"
echo "Checking inference"
VLLM_BASE_URL="$MODEL_BASE_URL" \
VLLM_API_KEY="$MODEL_API_KEY" \
VLLM_CONTAINER_NAME="$CONTAINER_NAME" \
VLLM_MODEL_NAME="$MODEL_NAME" \
VLLM_WAIT_TIMEOUT_SEC="$STARTUP_TIMEOUT_SEC" \
VLLM_EXPECTED_GPU_COUNT="$GPU_COUNT" \
    "${SCRIPT_DIR}/inference/test.sh"

export OPENAI_BASE_URL="$MODEL_BASE_URL"
export OPENAI_API_KEY="$MODEL_API_KEY"
export REACT_AGENT_BASE_URL="$MODEL_BASE_URL"
export REACT_AGENT_API_KEY="$MODEL_API_KEY"
export PYTHONPATH="${SCRIPT_DIR}${PYTHONPATH:+:${PYTHONPATH}}"

echo "STAGE2_PHASE=harbor"
echo "Running Harbor with agent=$HARBOR_AGENT model=$MODEL_NAME"
cd "$PROJECT_DIR"

"$HARBOR_BIN" run \
    --path "$SWE_MERA_TASKS_DIR" \
    --agent "$HARBOR_AGENT" \
    --model "openai/${MODEL_NAME}" \
    --jobs-dir "$SWE_MERA_JOBS_DIR" \
    --n-attempts 1 \
    --n-concurrent "$N_CONCURRENT" \
    --agent-timeout-multiplier "$AGENT_TIMEOUT_MULTIPLIER" \
    --yes
