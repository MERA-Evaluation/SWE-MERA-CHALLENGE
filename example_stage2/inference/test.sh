#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${VLLM_BASE_URL:-http://127.0.0.1:8000/v1}"
API_KEY="${VLLM_API_KEY:-dummy}"
CONTAINER_NAME="${VLLM_CONTAINER_NAME:-inference_container}"
MODEL_NAME="${VLLM_MODEL_NAME:?VLLM_MODEL_NAME is required}"
WAIT_TIMEOUT_SEC="${VLLM_WAIT_TIMEOUT_SEC:-1800}"

test_tmp_dir="$(mktemp -d)"
trap 'rm -rf "$test_tmp_dir"' EXIT

models_response="$test_tmp_dir/models.json"
chat_response="$test_tmp_dir/chat.json"
request_body="$test_tmp_dir/request.json"

deadline=$((SECONDS + WAIT_TIMEOUT_SEC))
echo "Waiting for ${BASE_URL}/models ..."
while ((SECONDS < deadline)); do
  if curl -fsS \
    --connect-timeout 2 \
    --max-time 10 \
    -H "Authorization: Bearer ${API_KEY}" \
    "${BASE_URL}/models" >"$models_response"; then
    break
  fi

  if docker container inspect "$CONTAINER_NAME" >/dev/null 2>&1 && \
    [[ "$(docker inspect -f '{{.State.Running}}' "$CONTAINER_NAME")" != "true" ]]; then
    echo "Container ${CONTAINER_NAME} stopped before the API became ready" >&2
    docker logs --tail 100 "$CONTAINER_NAME" >&2
    exit 1
  fi
  sleep 2
done

if [[ ! -s "$models_response" ]]; then
  echo "Timed out waiting for vLLM after ${WAIT_TIMEOUT_SEC}s" >&2
  docker logs --tail 100 "$CONTAINER_NAME" >&2 || true
  exit 1
fi

python3 - "$MODEL_NAME" "$request_body" <<'PY'
import json
import sys
from pathlib import Path

model_name, target = sys.argv[1:]
request = {
    "model": model_name,
    "messages": [
        {
            "role": "user",
            "content": (
                "Call the bash tool exactly once with the command pwd. "
                "Do not answer in plain text."
            ),
        }
    ],
    "tools": [
        {
            "type": "function",
            "function": {
                "name": "bash",
                "description": "Run a shell command",
                "parameters": {
                    "type": "object",
                    "properties": {"command": {"type": "string"}},
                    "required": ["command"],
                    "additionalProperties": False,
                },
            },
        }
    ],
    "tool_choice": "auto",
    "temperature": 0,
    "max_tokens": 256,
}
Path(target).write_text(json.dumps(request), encoding="utf-8")
PY

curl -fsS \
  --max-time 300 \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer ${API_KEY}" \
  --data-binary "@$request_body" \
  "${BASE_URL}/chat/completions" >"$chat_response"

python3 - "$MODEL_NAME" "$models_response" "$chat_response" <<'PY'
import json
import sys
from pathlib import Path

expected_model = sys.argv[1]
models = json.loads(Path(sys.argv[2]).read_text())
chat = json.loads(Path(sys.argv[3]).read_text())

model_ids = [item.get("id") for item in models.get("data", [])]
assert expected_model in model_ids, (
    f"served model is missing; received model IDs: {model_ids}"
)

assert chat.get("object") == "chat.completion", chat
assert chat.get("model") == expected_model, chat.get("model")
choices = chat.get("choices") or []
assert choices, "response has no choices"
choice = choices[0]
assert choice.get("finish_reason") == "tool_calls", choice.get("finish_reason")

message = choice.get("message") or {}
tool_calls = message.get("tool_calls") or []
assert len(tool_calls) == 1, f"expected one tool call, got {len(tool_calls)}"
tool_call = tool_calls[0]
assert isinstance(tool_call.get("id"), str) and tool_call["id"], tool_call
assert tool_call.get("type") == "function", tool_call

function = tool_call.get("function") or {}
assert function.get("name") == "bash", function
arguments = json.loads(function.get("arguments") or "{}")
assert isinstance(arguments, dict), arguments
assert arguments.get("command") == "pwd", arguments

print(json.dumps(chat, ensure_ascii=False, indent=2))
print("\nPASS: vLLM returned a valid OpenAI bash tool call for pwd.")
PY
