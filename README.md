<div align="center">

# SWE-MERA-CHALLENGE

**Fresh, uncontaminated real-world software engineering tasks across Go, Python, PHP, and more.**

<p>
  <img alt="runner" src="https://img.shields.io/badge/runner-Harbor%200.22.0-6e40c9?style=flat-square&labelColor=0d1117">
  <img alt="metric" src="https://img.shields.io/badge/metric-pass%401-1a7f37?style=flat-square&labelColor=0d1117">
  <img alt="tasks" src="https://img.shields.io/badge/tasks-49-1f6feb?style=flat-square&labelColor=0d1117">
  <img alt="languages" src="https://img.shields.io/badge/Go%2018%20·%20Python%2016%20·%20PHP%2015-24292f?style=flat-square&labelColor=0d1117">
</p>

</div>

## Setup

### Requirements

uv, Docker, Git, and 60 GB of free disk space.

<details>
<summary>Detailed requirements</summary>

| Component | Version or capacity | Why |
| :-- | :-- | :-- |
| uv | `>= 0.8.0` | Manages Python and the virtual environment. |
| Python | `3.12`, managed by uv | Runs the pinned Harbor environment. |
| Docker | `>= 24` with the daemon running | Every task executes in a container. |
| Git | `>= 2.30` | Used for cloning and diff handling. |
| Disk | `>= 60 GB` free | Task images are large, especially the PHP images. |
| CPU | `>= 2` cores per concurrent task | Each container is limited to two cores. |
| RAM | `>= 4 GB` per concurrent task | Each container is limited to 4 GB. |
| Architecture | `x86_64`, or Docker with `linux/amd64` emulation | Task images are amd64-only. |

</details>

### Install

uv pins Python 3.12, creates the virtual environment, downloads the interpreter when necessary, and installs the pinned dependencies:

```bash
git clone https://github.com/MERA-Evaluation/SWE-MERA-CHALLENGE.git
cd SWE-MERA-CHALLENGE

uv python pin 3.12
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements.txt
uv run --python .venv/bin/python -- harbor --version
```

The last command must print `0.22.0`.

<details>
<summary>If uv or Python 3.12 is not installed</summary>

If Python 3.12 is missing, no separate Python installation is required: `uv venv --python 3.12 .venv` downloads a managed interpreter automatically.

If `uv` itself is missing, install it using the [official uv installation guide](https://docs.astral.sh/uv/getting-started/installation/), then rerun the setup commands.

</details>

### Model configuration

Store provider credentials in `.env`, then select the model and agent using the `harbor run` arguments below.

```bash
cp configs/.env.example .env
vim .env
```

<details>
<summary>Credential troubleshooting</summary>

Harbor resolves models through LiteLLM.

Configure one provider and delete the rest. Empty variables are ignored, but an incorrect or expired key can cause a `401` even when another provider is configured correctly. Keep the default `*_API_BASE` or `*_BASE_URL` unless you use a proxy, regional endpoint, or local server.

</details>

<details>
<summary>Set up OpenRouter, OpenAI, Anthropic, or Gemini</summary>

Each block below is a complete configuration.

**OpenRouter** with `--model openrouter/qwen/qwen3.7-flash`:

```dotenv
OPENROUTER_API_KEY=YOUR_OPENROUTER_API_KEY
OPENROUTER_API_BASE=https://openrouter.ai/api/v1
```

**OpenAI** with `--model openai/gpt-5.4`:

```dotenv
OPENAI_API_KEY=YOUR_OPENAI_API_KEY
OPENAI_BASE_URL=https://api.openai.com/v1
```

**Anthropic** with `--model anthropic/claude-sonnet-4-6`:

```dotenv
ANTHROPIC_API_KEY=YOUR_ANTHROPIC_API_KEY
```

**Gemini** with `--model gemini/gemini-3.1-pro-preview`:

```dotenv
GEMINI_API_KEY=YOUR_GEMINI_API_KEY
```

</details>

<details>
<summary>Set up a self-hosted model</summary>

To use an **OpenAI-compatible local or self-hosted model**, such as vLLM, SGLang, TGI, llama.cpp, LM Studio, Ollama, or a compatible proxy, configure the following variables:

```dotenv
OPENAI_API_KEY=dummy
OPENAI_BASE_URL=http://host.docker.internal:8000/v1
```

</details>

<details>
<summary>Endpoint details</summary>

| Rule | Detail |
| :-- | :-- |
| URL shape | End it with `/v1`. Do not append `/chat/completions`; the client adds that route. |
| From a container | `localhost` means the container. Use `host.docker.internal` or the host IP. |
| API key | Most local servers ignore it, but the client requires a non-empty value such as `dummy`. |
| Model name | Pass `--model openai/<name>`, using the name returned by `curl http://localhost:8000/v1/models` from the host shell. Keep `host.docker.internal` in `.env` for the agent container. |
| Endpoint | Agents use Chat Completions at `/v1/chat/completions`. A server exposing only `/v1/responses` is not compatible. |

The same OpenAI variables work with a corporate gateway or an Azure-style proxy; only the URL changes. Harbor loads `.env` through `--env-file .env`, and `.env` is ignored by Git.

</details>

<details>
<summary>Tips and tricks</summary>

> **Tip:** Images are pulled once and cached by Docker. The first run is slow; later runs are faster. On rented hardware, warm the cache on a few tasks before launching the full sweep.

> **Note:** Verification times vary widely. A Go task can finish in under a minute, while a large PHP task runs tens of thousands of `pass_to_pass` tests and can take tens of minutes on two cores. On arm64, amd64 emulation is several times slower and can push the largest PHP tasks into the 3600 s verifier timeout. Prefer native `x86_64` hardware for a scoring sweep.

</details>

## Run

### Smoke test

The oracle applies the reference patch. It should finish with a reward of `1`.

```bash
uv run --python .venv/bin/python -- harbor run \
  --path tasks \
  --include-task-name go-001 \
  --agent oracle \
  --jobs-dir jobs/smoke \
  --n-attempts 1 \
  --n-concurrent 1 \
  --yes
```

<a name="troubleshooting"></a>
<details>
<summary>Smoke test and troubleshooting</summary>

If the smoke test cannot start, verify that Docker is installed, its daemon is running, and it can execute the benchmark's `linux/amd64` images:

```bash
docker info
docker run --rm --platform=linux/amd64 hello-world
```

| Symptom | Cause and fix |
| :-- | :-- |
| `docker: command not found` | Install Docker Engine or Docker Desktop, then rerun the checks above. |
| Cannot connect to the Docker daemon | Start Docker and wait until `docker info` succeeds. |
| `harbor --version` prints something other than `0.22.0` | Rerun the uv setup commands from [Install](#install). |
| `no match for platform in manifest` | Enable `linux/amd64` emulation or use an `x86_64` machine. |
| `range of CPUs is from 0.01 to N` | Give Docker at least two cores per concurrent task. |
| The oracle reward is not `1` | Confirm that Docker is running and enough disk space is available. |
| pass@1 is unexpectedly low | Check `pass_to_pass` regressions in the verifier logs under `jobs/`. |
| Tasks time out | Lower `--n-concurrent`; the machine is short of CPU or memory. |
| API authentication fails | Check the selected key and remove invalid credentials for unused providers from `.env`. |

</details>

###  Run the full benchmark

```bash
uv run --python .venv/bin/python -- harbor run \
  --path tasks \
  --agent mini-swe-agent \
  --model openrouter/qwen/qwen3.7-flash \
  --env-file .env \
  --jobs-dir jobs/run-001 \
  --n-attempts 1 \
  --n-concurrent 2 \
  --yes
```
> **Estimated cost:** Approximately 1.5 USD for a full run with this model.
<details>
<summary>Run with OpenHands, Claude Code, or a custom agent</summary>

#### OpenHands

```bash
uv run --python .venv/bin/python -- harbor run \
  --path tasks \
  --agent openhands \
  --model openrouter/qwen/qwen3.7-flash \
  --env-file .env \
  --jobs-dir jobs/openhands \
  --n-attempts 1 \
  --n-concurrent 2 \
  --yes
```

#### Claude Code

```bash
uv run --python .venv/bin/python -- harbor run \
  --path tasks \
  --agent claude-code \
  --model anthropic/claude-sonnet-4-6 \
  --env-file .env \
  --jobs-dir jobs/claude-code \
  --n-attempts 1 \
  --n-concurrent 2 \
  --yes
```

#### Custom agent

Replace `your_package.agent:CustomAgent` with the agent's Python import path.

```bash
uv run --python .venv/bin/python -- harbor run \
  --path tasks \
  --agent your_package.agent:CustomAgent \
  --model openai/gpt-5.4 \
  --env-file .env \
  --jobs-dir jobs/custom-agent \
  --n-attempts 1 \
  --n-concurrent 2 \
  --yes
```

The package must be importable from `.venv`. Pass custom constructor arguments with the repeatable `--agent-kwarg key=value` option.

</details>

## Submit results

Point the packaging script at the timestamped job directory:

```bash
scripts/create-submission.sh jobs/run-001/2026-08-30__05-45-50
```

This creates `sample_submission.zip`. Attach that file to the submission form on the competition website.

## Rules

- Give each task exactly one attempt.
- Submit only patches produced by the agent during the run.
- Do not use gold patches, evaluation tests, or test-specific workarounds.
- Retain the Harbor job directory and trajectories for verification.
<a name="task-overview"></a>
<details>
<summary><strong>Task overview</strong></summary>

Every task is a real defect from a real repository. The repository is checked out at the parent commit of the upstream fix, the agent receives the original issue description, and it works inside `/testbed`. After the agent stops, the verifier applies the test patch from the upstream pull request and runs the suite.

A task counts as **resolved** only when both conditions hold:

1. every test listed in `fail_to_pass` passes; these tests failed before the fix;
2. every test listed in `pass_to_pass` still passes, so no regression is allowed.

The leaderboard metric is **pass@1**. Each task receives exactly one attempt, and the score is the share of all 49 tasks resolved by that attempt. Additional attempts do not improve the result.

Regression coverage matters. Some tasks list tens of thousands of `pass_to_pass` tests; `php-001` alone lists 46,118. A patch that fixes the target tests by breaking other behaviour scores zero for that task.

The benchmark uses the [Harbor](https://github.com/laude-institute/harbor) task format. `dataset.toml` pins the task packages, and every task uses a Docker environment published on Docker Hub, so nothing needs to be built from source.

| | |
| :-- | :-- |
| Tasks | 49: 18 Go, 16 Python, 15 PHP |
| Difficulty | 10 easy, 23 medium, 16 hard |
| Per-task limits | 2 CPU, 4 GB RAM, 16 GB disk, 3600 s agent, 3600 s verifier |
| Image platform | `linux/amd64` |
| Runner | Harbor 0.22.0, pinned in `requirements.txt` |
| Metric | pass@1 over all 49 tasks |
| Deliverable | `sample_submission.zip` |

</details>
<a name="task-structure"></a>
<details>
<summary><strong>Task structure</strong></summary>

Repository layout:

```text
SWE-MERA-CHALLENGE/
├── dataset.toml              task list with pinned package digests
├── requirements.txt          fully pinned Harbor runner environment
├── tasks/<task-id>/          49 task definitions
├── scripts/
│   └── create-submission.sh   packages a Harbor run as sample_submission.zip
└── configs/
    └── .env.example          API key template
```

A single task looks like this:

```text
tasks/go-001/
├── instruction.md            agent prompt with issue, scope, and completion criteria
├── task.toml                 language, difficulty, repo, base_commit, and limits
├── environment/
│   └── Dockerfile            derives from the public image and strips fix/test artifacts
├── solution/
│   ├── fix.patch             upstream maintainer patch, for the oracle only
│   └── solve.sh              oracle agent that applies fix.patch
└── tests/
    ├── config.json           build/test commands, fail_to_pass, and pass_to_pass
    ├── test.patch            tests from the upstream pull request
    ├── run_tests.py          applies tests, runs the suite, and parses junit.xml
    ├── parse                 report parser
    └── test.sh               verifier entrypoint
```

| Property | Practical consequence |
| :-- | :-- |
| `/testbed` is the only writable work area | Changes made outside it never reach the diff. |
| Git history is truncated to one snapshot | The upstream fix commit cannot be recovered from the repository. |
| The image is stripped of `fix.patch`, `test.patch`, and gold evaluation helpers | No reference solution is reachable from inside the container. |
| Tests are injected only during verification | The agent cannot read `fail_to_pass` or tailor code to test names. |
| The deliverable is a Git diff from `/testbed` | The collect hook includes modified, deleted, binary, and untracked files; work does not need to be committed, but it must remain inside `/testbed`. |
| Toolchains differ by language | Go uses `gotestsum`, PHP uses `composer install` with PHPUnit or Pest, and Python uses `pip install -e .` and `pytest`. |
| Results use `junit.xml` | Test identifiers in `config.json` match the parsed report rather than raw console output. |

</details>
<a name="how-to-progress"></a>
<details>
<summary><strong>How to progress</strong></summary>

### Validate the harness

Run the oracle before testing a model. It applies the upstream patch, so the run must finish with a reward of `1`. Any other result points to the environment rather than the model.

```bash
uv run --python .venv/bin/python -- harbor run \
  --path tasks \
  --include-task-name go-001 \
  --agent oracle \
  --jobs-dir jobs/smoke \
  --n-attempts 1 \
  --n-concurrent 1 \
  --yes
```

### Run a model

Pass `--n-attempts 1` explicitly even though it is Harbor's default, so the run cannot inherit another value from configuration or a shell alias.

```bash
uv run --python .venv/bin/python -- harbor run \
  --path tasks \
  --agent mini-swe-agent \
  --model openrouter/qwen/qwen3.7-flash \
  --env-file .env \
  --jobs-dir jobs/run-001 \
  --n-attempts 1 \
  --n-concurrent 2 \
  --yes
```

Harbor agents include `terminus-2`, `mini-swe-agent`, `swe-agent`, `openhands`, `claude-code`, and `codex`. Run `uv run --python .venv/bin/python -- harbor run --help` for the complete list, or pass an import path for a custom implementation.

Choose `--n-concurrent` for the available hardware. Each concurrent task can consume two CPU cores and 4 GB of RAM, so four tasks imply at least eight cores and 16 GB of RAM.

### Run a subset

Use a mixed-language subset while tuning:

```bash
uv run --python .venv/bin/python -- harbor run \
  --path tasks \
  --include-task-name go-012 \
  --include-task-name php-001 \
  --include-task-name py-005 \
  --agent oracle \
  --jobs-dir jobs/run-002 \
  --n-attempts 1 \
  --yes
```

### Job output

Harbor creates one timestamped job directory and one `<task-id>__<suffix>` directory per trial:

```text
jobs/run-001/2026-08-21__14-44-53/
├── config.json
├── lock.json
├── result.json
├── job.log
└── go-001__cEAJUzd/
    ├── config.json
    ├── lock.json
    ├── result.json
    ├── trial.log
    ├── agent/
    ├── artifacts/
    │   ├── manifest.json
    │   └── logs/artifacts/model_patch.diff
    └── verifier/
        ├── apply_test_patch.log
        ├── command_build.log
        ├── command_test.log
        ├── test-stdout.txt
        ├── parse.log
        ├── parse_result.json
        ├── report.json
        └── reward.txt
```

At job level, `config.json` records the launched task list, `lock.json` records the Harbor version, concurrency, and resolved trials, `result.json` holds aggregate and per-evaluation rewards, and `job.log` records the run.

Inside each trial, `config.json` records the task path, trial name, and job id; `lock.json` records the task digest, agent, and environment; `result.json` records `task_name`, `agent_info`, `verifier_result.rewards.reward`, and timings. The `agent/` directory contains the agent's logs, trajectory, and tool calls. The `verifier/` directory contains build, test, parser, and reward outputs.

`artifacts/manifest.json` records what Harbor copied from the container, while `artifacts/logs/artifacts/` contains everything the agent left in `/logs/artifacts`. In `verifier/`, `parse_result.json` lists passed, failed, skipped, and ignored tests; `report.json` records build and test return codes, whether JUnit output was found, and the reward; `reward.txt` is `1` for a resolved task and `0` otherwise.

### Patch collection

The harness, not the agent, produces the submission patch. Every `tasks/*/task.toml` has a `[[verifier.collect]]` hook with a 120-second timeout. Harbor runs it after the agent phase and before artifact collection. Using a private Git index, the hook runs `git add -A`, removes the excluded files from that index, and writes `git diff --cached --binary` against the task snapshot to `/logs/artifacts/model_patch.diff`. Harbor then copies it to `<trial>/artifacts/logs/artifacts/model_patch.diff`.

The hook runs for every agent, including agents that do not export a patch, time out, or use the oracle.

| Property | Detail |
| :-- | :-- |
| Timing | The patch is collected before the test patch is applied, so test files cannot leak into the diff. |
| Baseline | The task snapshot root commit, so committed agent work is included. |
| Contents | Modified, added, deleted, untracked, and binary files through a binary Git diff. |
| Exclusions | Git-ignored files, `junit.xml`, `task_tests.json`, `*.orig`, and `*.rej`. |
| Side effects | A private Git index keeps the agent's index and `git status` unchanged. |
| Failure | Harbor records a warning in `trial.log`; inspect it before packaging the run. |

Do not delete the collect hook. Without it, solved tasks still produce no patches and cannot be submitted. Keep the complete job directory until `sample_submission.zip` has been created and uploaded.

</details>
<a name="rules-and-penalties"></a>
<details>
<summary><strong>Full rules and penalties</strong></summary>

> **Warning:** Submissions matching the gold solution will be penalised. Gold patches under `tasks/*/solution/` exist only so the oracle can validate the harness. Copying `fix.patch`, cosmetically rewording it, or otherwise reusing it is a violation and may invalidate the result.

In addition:

- Submit only patches produced by the agent during the run.
- Give every task one attempt.
- Do not modify `tasks/*/tests/` or tailor code to test names or structure.
- Do not disable, delete, or rewrite tests inside `/testbed`.
- Retain trajectories so the origin of each patch can be verified.

</details>
