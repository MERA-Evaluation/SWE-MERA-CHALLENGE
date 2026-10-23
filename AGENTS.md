# SWE-MERA agent workflow

Use this guide when helping a participant set up and run SWE-MERA. The project
root is the directory containing this file, `requirements.txt`, and `tasks/`;
it may have a different name from `SWE-MERA-CHALLENGE`. Run commands in Bash
from that actual directory unless stated otherwise. Read `requirements.txt`
and the relevant runner before changing commands.

**The competition is currently in Stage 2: participants provide their own
inference.** Stage 1 below is the local OpenRouter development workflow. Its
patch-only submission format is no longer accepted by the current evaluator.

## Execution order and communication

Treat this file as a staged workflow, not a checklist to execute all at once.
A general request to "execute AGENTS.md" starts with Stage 1. An explicit user
request to work on Stage 2 can start there directly. A request to edit this
guide only authorizes editing it; do not resume benchmarks as part of that edit.

- Resolve the current prerequisite before asking for later prerequisites.
  First check Docker, uv, Harbor, and network-policy support. Only after those
  checks pass, request the OpenRouter key and run oracle validation. Oracle may
  run while the user configures the key. Both must pass before the baseline.
- Continue authorized work automatically when its prerequisites pass. Do not
  ask for generic permission at every step. Ask for a user action only when
  it is necessary, or for a choice explicitly required by this workflow.
- While Stage 1 is active or blocked, do not check GPUs, request a GPU server,
  discuss GPU setup, create `submission_stage2`, or build/package a Stage 2 ZIP.
  Do not append Stage 2 prerequisites to a Stage 1 progress or final message.
  Importing the example custom agent for a local Stage 1 comparison is allowed.
- After the baseline, report its results and ask which agent/model to compare
  next, or whether the user wants to proceed to Stage 2. Enter Stage 2 when the
  user selects it or has already explicitly requested that transition. Do not
  turn a blocked local run into unrelated submission preparation.
- Respond in the user's language. Use concrete paths from this checkout, not
  a literal `SWE-MERA-CHALLENGE` path if the directory has another name.

When a step needs user action, make the handoff actionable in one message:

1. State the current step, the failed check, and what the failure means.
2. Give the recommended next action with numbered UI steps or copyable commands,
   the exact file path if relevant, and an official link for installation.
3. State what success looks like and what to reply (for example, "готово").
4. Explain which checks you will repeat and which step will then continue.

Do not stop at "a compatible Docker/Linux environment is required", "configure
access", or "put a key in .env". Explain how to do it. Give the most relevant
remedy first; present a fallback only if that remedy is unavailable or fails.
Report completed work separately from blocked work, and never call a started
or failed run a successful validation. Keep unrelated future requirements out
of the handoff. Finish with the action needed now, not a list of future blockers.

## Stage 1: local evaluation through OpenRouter

### 1. Check prerequisites and install Harbor

Check Docker before starting any benchmark:

```bash
command -v docker
docker --version
docker info
docker compose version
docker run --rm --platform=linux/amd64 hello-world
df -h .
```

- If Docker is missing, ask the user to install Docker Engine or Docker Desktop
  using the [official Docker installation guide](https://docs.docker.com/get-started/get-docker/).
  Wait for installation, then repeat the checks.
- If a tool sandbox denies access to Docker's socket, use the tool's approved
  escalation mechanism before concluding the daemon or user permissions are
  broken. A sandbox denial does not mean Docker itself is unavailable.
- If Docker exists but `docker info` still fails, diagnose the actual error.
  On macOS, if Docker Desktop is stopped, ask the user to open
  `/Applications/Docker.app`, wait for the engine to start, and reply "готово";
  then repeat `docker info`. For a permission or context error, identify the
  affected socket/context and give the specific fix supported by the evidence.
  A working CLI alone is insufficient.
- Require Docker 24 or newer, Compose, and support for `linux/amd64` images.
  Prefer native x86_64 for full runs; emulation can cause verifier timeouts.
- Allow at least 60 GB of free disk space and approximately two CPU cores and
  4 GB RAM per concurrent task. Start with concurrency 1 or 2.

Check uv and the project-local Harbor installation:

```bash
command -v uv
uv --version
if [ -x .venv/bin/harbor ]; then
  .venv/bin/harbor --version
fi
```

If uv is missing, ask the user to install it using the
[official uv installation guide](https://docs.astral.sh/uv/getting-started/installation/),
then reopen their shell or update `PATH`. Do not continue until `uv --version`
works. Use uv 0.8.0 or newer.

Once uv is available, install missing Harbor dependencies yourself using the
repository's pinned environment:

```bash
uv python pin 3.12
# Create the environment only if it is missing; preserve an existing environment.
if [ ! -x .venv/bin/python ]; then
  uv venv --python 3.12 .venv
fi
uv pip install --python .venv/bin/python -r requirements.txt
uv run --python .venv/bin/python -- harbor --version
```

The current `requirements.txt` pins `harbor==0.21.0`. Verify that version rather
than relying on a globally installed Harbor. uv can download Python 3.12 when
needed. If installation needs a user action you cannot perform, explain the
failure and ask the user to run the same installation commands, then recheck.

For a standalone CLI, Harbor also supports `uv tool install --python 3.12
'harbor==0.21.0'`; use the project environment above for this repository so the
remaining dependencies also match. See the
[Harbor installation instructions](https://github.com/harbor-framework/harbor#installation).

#### Check network-policy support before starting oracle

The tasks use `network_mode = "allowlist"`. Docker's version and a successful
`hello-world` run do not establish that Harbor can enforce this policy. Inspect
the installed Harbor Docker backend and its kernel probe before a full run.
For the pinned Harbor 0.21.0, the probe requires `CONFIG_NFT_FIB_INET=y` or `m`
when the Docker VM exposes `/proc/config.gz`. This is a property of the Linux
kernel used by Docker, not a Python dependency or an OpenRouter setting.

Use the probe image from the installed package rather than guessing an image
version. This diagnostic prints the kernel and distinguishes unsupported from
unavailable kernel configuration:

```bash
.venv/bin/python - <<'PY'
import subprocess
from harbor.environments.docker.docker import DockerEnvironment

script = r'''
uname -r
if [ ! -r /proc/config.gz ]; then
  echo "UNKNOWN: /proc/config.gz is unavailable"
  exit 2
fi
if zcat /proc/config.gz | grep -E '^CONFIG_NFT_FIB_INET=[ym]$'; then
  echo "PASS: required kernel option is enabled"
else
  echo "FAIL: CONFIG_NFT_FIB_INET is not enabled"
  exit 1
fi
'''
result = subprocess.run([
    "docker", "run", "--rm",
    DockerEnvironment._EGRESS_CONTROL_KERNEL_PROBE_IMAGE,
    "sh", "-c", script,
], timeout=120)
raise SystemExit(result.returncode)
PY
```

An image-pull, timeout, or socket error is not evidence of a missing kernel
option. Diagnose it separately. `UNKNOWN` also does not mean unsupported:
inspect another available kernel configuration or verify the backend's actual
network-policy support before declaring compatibility. A passing kernel check
is a prerequisite, not a replacement for successful oracle validation.

If the Docker Desktop kernel explicitly lacks `CONFIG_NFT_FIB_INET`, do not
launch all oracle trials or ask for the API key yet. Give these steps, adapted
to the user's language and observed installation:

1. Open Docker Desktop, open the Docker menu, and select **Check for updates**.
   Install the available full Docker Desktop update and let it restart. Updating
   only the Docker CLI or reinstalling Harbor does not replace the Docker VM's
   kernel. See the [official update instructions](https://docs.docker.com/desktop/troubleshoot-and-support/faqs/releases/).
   If the in-app update is unavailable, use the
   [official Mac installer](https://docs.docker.com/desktop/setup/install/mac-install/)
   for the machine's chip and supported macOS version.
2. Wait until the engine is running and reply "готово". Explain that you will
   repeat `docker info`, the `linux/amd64` check, and the kernel probe yourself.
   Do not promise that an update fixes this specific kernel option: confirm it.
3. Only if updating is unavailable or the probe still fails, propose running
   the checkout on a Linux machine with Docker Engine, Compose, the resource
   requirements above, and verified network-policy support. Ask whether the
   user already has a machine and how to connect; never request passwords or
   private keys in chat. Once the host is known, give concrete transfer and
   setup commands for that host, preserve existing work, and rerun the checks.

For example, a current-stage handoff can say: "Проверка остановилась до запуска
задач: ядро Docker не поддерживает нужное сетевое ограничение. Откройте Docker
Desktop → меню Docker → Check for updates, установите обновление и дождитесь
запуска Docker. Напишите ‘готово’: я повторю проверку ядра; если она пройдёт,
перейду к настройке ключа и oracle." Include the official link and the observed
failure in the actual reply. Do not add a GPU request or an API-key request to
this Docker handoff. Do not weaken task network policies, change verifiers, or
bypass Harbor's capability check to make the run start.

### 2. Ask the user to configure the OpenRouter key

Enter this step only after the environment checks above pass. Check whether
the actual project root already has a usable key without displaying it. If it
does, verify authentication and continue without asking the user to re-enter it.
Otherwise create a template `.env` next to this file, adding only missing
settings and preserving existing values. Make sure Git ignores it and set
permissions to `600` before asking the user to edit it. This is separate from
the parent evaluator's `.env`, which contains ODS credentials.

```dotenv
OPENAI_API_BASE=https://openrouter-proxy.sberai-rnd.ru/
OPENAI_API_KEY=sk-REPLACE_WITH_YOUR_KEY
SWE_MERA_MODEL=qwen35-9b
```

Give the user these concrete instructions, with the actual absolute path filled
in (never leave a placeholder path in the message):

1. Open the linked `.env` file in the project root. On macOS, also provide
   `open -e "/actual/absolute/project/path/.env"`, substituting the real path.
2. Replace only `sk-REPLACE_WITH_YOUR_KEY` in `OPENAI_API_KEY=...` with the key
   issued for `https://openrouter-proxy.sberai-rnd.ru/`. Leave the base URL and
   model as shown unless the organizer provided different verified settings.
   Explain that the placeholder is not a working key.
3. Save the file (Cmd+S on macOS) and reply "готово". Say that you will check
   authentication and the available model, without printing the credential.

If the user has no key, explain that they need access credentials for this
competition proxy from its organizers/access administrator. Do not invent a
registration page or assume a key created on `openrouter.ai` works with the
proxy. Ask only for missing non-secret access details. Do not ask for a key in
chat, print it, commit it, or include it in a submission archive. Reject empty
or unchanged placeholder values before making authentication requests. While
waiting for the key, proceed with oracle because its prerequisites now pass.

The baseline is **Qwen3.5-9B**, requested as `qwen35-9b`. The proxy's actual
served model ID must be verified before the run; do not silently select a
different model. These are shell assignments: there must be no spaces around
`=`. The equivalent export syntax is `export OPENAI_API_BASE="https://openrouter-proxy.sberai-rnd.ru/"`.

After the user saves the file, check that Git ignores it, restrict its permissions,
and load it without displaying its contents:

```bash
git check-ignore .env
chmod 600 .env
set -a
. ./.env
set +a
: "${OPENAI_API_KEY:?Put your OpenRouter key in .env first}"
: "${OPENAI_API_BASE:?Set the OpenRouter proxy base URL in .env}"
: "${SWE_MERA_MODEL:?Set the model ID in .env}"
export OPENAI_BASE_URL="$OPENAI_API_BASE"
export REACT_AGENT_BASE_URL="$OPENAI_API_BASE"
export REACT_AGENT_API_KEY="$OPENAI_API_KEY"
```

`OPENAI_BASE_URL` is the client-compatible alias; `REACT_AGENT_*` configures the
Stage 2 custom agent when reused locally. Keep all endpoint aliases consistent.
Remove or update stale aliases for this provider in `.env`: Harbor's
`--env-file` reloads the file and overrides exported values.

Verify authentication and list model IDs without logging credentials:

```bash
.venv/bin/python - <<'PY'
import os
import httpx

base = os.environ["OPENAI_API_BASE"].rstrip("/")
response = httpx.get(
    base + "/models",
    headers={"Authorization": "Bearer " + os.environ["OPENAI_API_KEY"]},
    timeout=30,
)
response.raise_for_status()
models = sorted(item["id"] for item in response.json()["data"])
print("Available models:", ", ".join(models))
assert os.environ["SWE_MERA_MODEL"] in models, "Select the proxy's exact Qwen3.5-9B ID in .env"
PY
```

A `401` or `403` needs an actionable handoff: report the status without headers
or secrets, link the exact `.env`, ask the user to verify that the key was issued
for this proxy and copied completely, save any correction, and reply "готово".
If a corrected key is still rejected, direct them to the organizer/access
administrator with the hostname and status code, never the key. For a `404`, verify
the proxy's API route: if it exposes `/v1/models`, change `OPENAI_API_BASE` to
`https://openrouter-proxy.sberai-rnd.ru/v1`, then reload the file and all aliases.
Do not append `/chat/completions` to the base URL. If the service uses a different
ID for Qwen3.5-9B, use that verified ID in `SWE_MERA_MODEL` and explain the mapping.
If no matching model is available, ask the user which model to use.

### 3. Validate the tasks with three oracle attempts

Run every public task three times using the oracle. This checks Docker, task
images, reference patches, and verifiers; it does not call a language model and
does not require an API key. It can run while waiting for the user's key.
Start it only after Docker/Harbor and network-policy preflight pass. If startup
fails before trials begin, diagnose that failure and report the actual completed
count; do not repeatedly launch the full job unchanged or prepare Stage 2 as
substitute progress.

```bash
uv run --python .venv/bin/python -- harbor run \
  --path tasks \
  --agent oracle \
  --jobs-dir jobs/oracle-validation \
  --n-attempts 3 \
  --n-concurrent 1 \
  --yes
```

The current public checkout contains 49 tasks, so this should produce 147
trials. Count the actual `tasks/*/task.toml` files if the dataset changes.
Inspect the timestamped job's `result.json`, every trial's `result.json`, and
`*/verifier/reward.txt`. Require exactly three completed trials per task, every
reward equal to `1`, and no errors, missing rewards, or timeouts. Do not treat a
zero process exit code as sufficient validation. Diagnose failures using
`trial.log` and `verifier/` before proceeding to model evaluation.

Oracle patches are reference solutions for infrastructure checks only. Never
submit them or reuse them in an agent. Keep oracle and model jobs separate.

### 4. Run the baseline on all public tasks

Once the oracle checks pass and the endpoint/model are verified, run the full
baseline with `mini-swe-agent` and Qwen3.5-9B:

```bash
uv run --python .venv/bin/python -- harbor run \
  --path tasks \
  --agent mini-swe-agent \
  --model "openai/${SWE_MERA_MODEL}" \
  --env-file .env \
  --jobs-dir jobs/stage1-baseline \
  --n-attempts 1 \
  --n-concurrent 2 \
  --yes
```

Use `openai/` because the supplied OpenRouter proxy is accessed through its
OpenAI-compatible API. For a scored model run, use exactly one attempt per task
and no task filters. Report resolved tasks, failures, timeouts, pass@1 over the
entire public set, and the timestamped job directory. Preserve logs, trajectories,
and collected patches. A completed model run need not achieve reward `1` on
every task; distinguish model failures from infrastructure errors.

### 5. Ask which agent to evaluate next, then run the full set

After reporting the baseline, ask the user:

> Would you like to use the custom agent from `example_stage2`, Claude Code,
> or another Harbor agent for a comparison, or proceed to Stage 2?
> If you want another local run, which agent and model should I use?

Show the choices from the installed Harbor, rather than assuming a newer
version's agent list:

```bash
uv run --python .venv/bin/python -- harbor run --help
.venv/bin/python - <<'PY'
from harbor.models.agent.name import AgentName
print("\n".join(sorted(agent.value for agent in AgentName)))
PY
```

Examples include `mini-swe-agent`, `swe-agent`, `claude-code`, `codex`,
`openhands`, `openhands-sdk`, `aider`, `terminus-2`, `goose`, `gemini-cli`,
`qwen-coder`, `opencode`, and `cursor-cli`. `oracle` and `nop` are diagnostic
agents. The full installed list is authoritative; upstream context is in the
[Harbor agent documentation](https://docs.harborframework.com/agents/pre-integrated-agents).
Wait for the user's choice before starting this additional full run.

For the custom agent, use the Stage 2 package explicitly. Change directory so
the top-level `custom_agent/` cannot shadow `example_stage2/custom_agent/`:

```bash
(
  cd example_stage2
  PYTHONPATH="$PWD" uv run --python ../.venv/bin/python -- harbor run \
    --path ../tasks \
    --agent custom_agent.react_bash_agent:ReactBashAgent \
    --model "openai/${SWE_MERA_MODEL}" \
    --env-file ../.env \
    --jobs-dir ../jobs/stage1-custom \
    --n-attempts 1 \
    --n-concurrent 2 \
    --yes
)
```

For another built-in agent, use the baseline command with the selected
`--agent`, compatible `--model`, and a separate jobs directory. Claude Code
uses `ANTHROPIC_API_KEY` or `ANTHROPIC_AUTH_TOKEN` and, for a compatible gateway,
`ANTHROPIC_BASE_URL`. Ask the user to put the required credentials in `.env`.
Do not assume an OpenAI Chat Completions proxy implements Anthropic Messages,
or that switching only `--agent` makes Qwen work with every client.

Run all tasks with the chosen setup and `--n-attempts 1`, then compare its
results with the baseline. Keep the benchmark tasks, verifiers, reference
solutions, and patch collection hooks unchanged.

## Stage 2: bring your own inference

Enter this section only when the user chooses Stage 2 or has already explicitly
requested it, after any local runs they requested have been handled. If the
user directly requests Stage 2, start here without requiring an unrelated
OpenRouter baseline. Until this transition, omit GPU/server requirements from
messages and do not prepare submission files or archives speculatively.

Explain that OpenRouter is for local development. The current competition
evaluates the submitted agent against the participant's own model server.
The evaluator builds an inference image and runs the agent on the organizer's
evaluation tasks. Public local runs use this checkout's 49 tasks; the current
ODS evaluator uses the separate 53-task TASK-6 set. Do not conflate their scores.

### 1. Prepare the inference and agent

Start a participant-owned directory from the Stage 2 example; preserve any
existing work instead of overwriting it:

```bash
mkdir submission_stage2
cp -R example_stage2/inference submission_stage2/inference
cp -R example_stage2/custom_agent submission_stage2/custom_agent
```

The example Dockerfile downloads `Qwen/Qwen3.5-9B` into the image at build time
and serves it using vLLM. Its served model ID is `qwen35-9b-chat`, an alias for
the same baseline model. A participant may change the model, server, and build
context. Now check available GPUs with `nvidia-smi`; GPU Docker requires the
[NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html).
If the active host cannot run this inference, explain that the current step
is now the Stage 2 model server, and ask whether the user has a Linux NVIDIA
GPU machine and how to connect without sharing credentials. For a known host,
inspect GPU models, count, and memory first, then give the exact missing setup
steps and verification commands. Do not stop at "a Linux server with NVIDIA
GPU is required". Ask for installation/configuration only when you cannot
perform the necessary action yourself.

Inspect the copied Dockerfile before building: the example uses three
data-parallel replicas across three GPUs and has hardware-specific FlashInfer settings.
Adjust these to the available GPU architecture and memory. The current official
runner allocates three GPUs; local settings must also fit the evaluation hardware.
Keep a pinned server version, include the required weights in the image, and
retain a model-appropriate tool-call parser. See the
[vLLM tool-calling documentation](https://docs.vllm.ai/en/stable/features/tool_calling/).

Create `submission_stage2/submission.yaml` with the current submission schema:

```yaml
agent: custom_agent
model: qwen35-9b-chat
```

Use `agent: mini_swe_agent` to select Harbor's `mini-swe-agent`; the underscore
spelling is specific to the submission schema. These are the two currently
accepted Stage 2 choices. Other Harbor agents, including Claude Code, are
available for local experiments but are not accepted as additional YAML values.

The YAML `model` value must exactly match the server's `--served-model-name`
and `/v1/models` response. It has no Harbor `openai/` provider prefix; the Harbor
CLI adds that prefix when selecting the model.

The production entrypoint is run from `SWE-MERA-CHALLENGE`:

```bash
./example_stage2/run.sh --username user_id
```

Keep the existing `--username` option name unchanged. It supplies the username
for runtime resources separately from `submission.yaml`; the ODS evaluator
assigns it automatically for submitted runs. The YAML contains only `agent` and
`model`. The following manual commands are useful for local inference development.

### 2. Build, start, and check the server

The following is a Linux GPU-host example using the copied three-GPU Dockerfile.
Use an unused container name and port. Do not remove someone else's container.
The bridge address makes the API reachable by both Harbor and its task containers.

```bash
export SWE_MERA_DOCKER_GATEWAY="$(docker network inspect bridge --format '{{(index .IPAM.Config 0).Gateway}}')"
export SWE_MERA_LOCAL_MODEL=qwen35-9b-chat
docker build --tag swe-mera-inference-local submission_stage2/inference
docker run --detach \
  --name swe-mera-inference-local \
  --gpus 3 \
  --ipc host \
  --ulimit memlock=-1:-1 \
  --ulimit stack=67108864:67108864 \
  --publish "${SWE_MERA_DOCKER_GATEWAY}:8000:8000" \
  swe-mera-inference-local

VLLM_BASE_URL="http://${SWE_MERA_DOCKER_GATEWAY}:8000/v1" \
VLLM_API_KEY=dummy \
VLLM_CONTAINER_NAME=swe-mera-inference-local \
VLLM_EXPECTED_GPU_COUNT=3 \
VLLM_MODEL_NAME="$SWE_MERA_LOCAL_MODEL" \
  bash example_stage2/inference/test.sh
```

Require the trusted test to pass before running Harbor. The image must start
its server through `ENTRYPOINT`/`CMD`, listen on `0.0.0.0:8000`, expose
`/v1/models` and `/v1/chat/completions`, and return valid OpenAI function tool
calls. The test checks the exact model ID and a `bash` call for `pwd`. Use
`docker logs swe-mera-inference-local` to diagnose startup problems; do not
weaken the trusted test.

### 3. Select the local model and run all public tasks

Switch every endpoint/key alias to the local server. Do not pass the Stage 1
`.env` here: Harbor would reload the OpenRouter settings over these exports.

```bash
export OPENAI_API_BASE="http://${SWE_MERA_DOCKER_GATEWAY}:8000/v1"
export OPENAI_BASE_URL="$OPENAI_API_BASE"
export OPENAI_API_KEY=dummy
export REACT_AGENT_BASE_URL="$OPENAI_API_BASE"
export REACT_AGENT_API_KEY=dummy

# For agent: mini_swe_agent, set this to mini-swe-agent instead.
export SWE_MERA_STAGE2_AGENT=custom_agent.react_bash_agent:ReactBashAgent
(
  cd submission_stage2
  PYTHONPATH="$PWD" uv run --python ../.venv/bin/python -- harbor run \
    --path ../tasks \
    --agent "$SWE_MERA_STAGE2_AGENT" \
    --model "openai/${SWE_MERA_LOCAL_MODEL}" \
    --jobs-dir ../jobs/stage2-local \
    --n-attempts 1 \
    --n-concurrent 2 \
    --yes
)
```

If another provider-specific key such as `MSWEA_API_KEY` is already set, clear
or update it so it cannot override the local key. Verify reachability from the
task containers as well as the host when using an installed agent.
Review the complete job results just as in Stage 1 and retain all artifacts.

### 4. Explain and package the Stage 2 submission

Package the submission after the preceding Stage 2 validation steps. If they
are blocked, report the current blocker and its remedy; do not create an
unvalidated ZIP unless the user explicitly requests a draft archive. Label
such a requested draft clearly and list the checks that have not run.

Submit a ZIP containing exactly one `submission.yaml`, the `inference/` Docker
build context, and `custom_agent/` when selecting the custom agent. The custom
package must include `__init__.py` and
`react_bash_agent.py` exporting `ReactBashAgent`.

```bash
(
  cd submission_stage2
  zip -r "../stage2-submission-$(date +%Y%m%d-%H%M%S).zip" \
    submission.yaml inference custom_agent \
    -x 'inference/test.sh' '*/__pycache__/*' '*.pyc' '*/.env' '*/.env.*'
)
```

For `mini_swe_agent`, omit `custom_agent` from the ZIP command. Include every
file the Docker build needs, but exclude secrets, local jobs, caches, and
downloaded images. Weights are fetched during the image build in the example.
Do not include Stage 1 patches as the Stage 2 deliverable.

The organizer supplies trusted runner and inference-test scripts; participant
changes to `run.sh` or `inference/test.sh` do not define the
evaluation. The submitted inference must run without the participant's
OpenRouter key. Hand the user the ZIP path and local validation results; upload
only when the user requests submission.
