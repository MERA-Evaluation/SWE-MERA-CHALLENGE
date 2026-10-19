#!/usr/bin/env bash
set -Eeuo pipefail

# Fixed evaluation settings. They are intentionally not read from submission.yaml.
GPU_COUNT=3
STARTUP_TIMEOUT_SEC=1800
DOCKER_GATEWAY="${SWE_MERA_DOCKER_GATEWAY:-172.17.0.1}"
MODEL_PORT="${SWE_MERA_MODEL_PORT:-8000}"
MODEL_API_KEY="dummy"

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
[[ -f "${SCRIPT_DIR}/inference/Dockerfile" ]] || fail \
    "inference/Dockerfile is missing"
[[ -x "${SCRIPT_DIR}/inference/test.sh" ]] || fail \
    "inference/test.sh is missing or not executable"

CONFIG="$("$PYTHON_BIN" - "$CONFIG_FILE" <<'PY'
import re
import sys
from pathlib import Path

import yaml

path = Path(sys.argv[1])
data = yaml.safe_load(path.read_text(encoding="utf-8"))

if not isinstance(data, dict):
    raise SystemExit("submission.yaml must contain a YAML object")

allowed = {"username", "agent", "model"}
unknown = sorted(set(data) - allowed)
if unknown:
    raise SystemExit(f"unknown submission fields: {', '.join(unknown)}")

username = data.get("username")
if not isinstance(username, str) or not re.fullmatch(
    r"[a-z0-9][a-z0-9_.-]{0,63}", username
):
    raise SystemExit(
        "username is required and must contain only lowercase letters, "
        "digits, '.', '_' or '-'"
    )

agent = data.get("agent")
if agent not in {"mini_swe_agent", "custom_agent"}:
    raise SystemExit("agent must be 'mini_swe_agent' or 'custom_agent'")

model = data.get("model")
if not isinstance(model, str) or not re.fullmatch(
    r"[A-Za-z0-9][A-Za-z0-9._/-]{0,127}", model
):
    raise SystemExit("model is required and contains unsupported characters")

print(username, agent, model, sep="\t")
PY
)"

IFS=$'\t' read -r USERNAME AGENT_KIND MODEL_NAME <<<"$CONFIG"

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

: "${SWE_MERA_TASKS_DIR:?SWE_MERA_TASKS_DIR is required}"
: "${SWE_MERA_JOBS_DIR:?SWE_MERA_JOBS_DIR is required}"

N_CONCURRENT="${SWE_MERA_N_CONCURRENT:-10}"
[[ "$N_CONCURRENT" =~ ^[1-9][0-9]*$ ]] || fail \
    "SWE_MERA_N_CONCURRENT must be a positive integer"

docker container inspect "$CONTAINER_NAME" >/dev/null 2>&1 && fail \
    "container already exists: $CONTAINER_NAME"

echo "Building $IMAGE_NAME"
docker build --tag "$IMAGE_NAME" "${SCRIPT_DIR}/inference"

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

echo "Checking inference"
VLLM_BASE_URL="$MODEL_BASE_URL" \
VLLM_API_KEY="$MODEL_API_KEY" \
VLLM_CONTAINER_NAME="$CONTAINER_NAME" \
VLLM_MODEL_NAME="$MODEL_NAME" \
VLLM_WAIT_TIMEOUT_SEC="$STARTUP_TIMEOUT_SEC" \
    "${SCRIPT_DIR}/inference/test.sh"

export OPENAI_BASE_URL="$MODEL_BASE_URL"
export OPENAI_API_KEY="$MODEL_API_KEY"
export REACT_AGENT_BASE_URL="$MODEL_BASE_URL"
export REACT_AGENT_API_KEY="$MODEL_API_KEY"
export PYTHONPATH="${SCRIPT_DIR}${PYTHONPATH:+:${PYTHONPATH}}"

echo "Running Harbor with agent=$HARBOR_AGENT model=$MODEL_NAME"
cd "$PROJECT_DIR"

uv run --python .venv/bin/python -- harbor run \
    --path "$SWE_MERA_TASKS_DIR" \
    --agent "$HARBOR_AGENT" \
    --model "openai/${MODEL_NAME}" \
    --jobs-dir "$SWE_MERA_JOBS_DIR" \
    --n-attempts 1 \
    --n-concurrent "$N_CONCURRENT" \
    --yes
