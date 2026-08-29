<div align="center">

# SWE-MERA-CHALLENGE

**49 issue-resolving tasks built from real open-source bug fixes.**

<p>
  <img alt="tasks" src="https://img.shields.io/badge/tasks-49-1f6feb?style=flat-square&labelColor=0d1117">
  <img alt="languages" src="https://img.shields.io/badge/Go%2018%20·%20Python%2016%20·%20PHP%2015-24292f?style=flat-square&labelColor=0d1117">
  <img alt="runner" src="https://img.shields.io/badge/runner-Harbor%200.22.0-6e40c9?style=flat-square&labelColor=0d1117">
  <img alt="metric" src="https://img.shields.io/badge/metric-pass%401-1a7f37?style=flat-square&labelColor=0d1117">
</p>

<sub>
<a href="#overview">Overview</a> ·
<a href="#task-anatomy">Task anatomy</a> ·
<a href="#installation">Installation</a> ·
<a href="#running-the-benchmark">Running</a> ·
<a href="#submitting-results">Submitting</a> ·
<a href="#local-scoring">Local scoring</a> ·
<a href="#rules-and-penalties">Rules</a> ·
<a href="#troubleshooting">Troubleshooting</a>
</sub>

</div>

---

## Overview

Every task in this benchmark is a real defect from a real repository. The repository is checked out at the parent commit of the upstream fix, the agent receives the original issue description and works inside `/testbed`. Once the agent stops, the verifier applies the test patch from the upstream pull request and runs the suite.

A task counts as **resolved** only when both conditions hold:

1. every test listed in `fail_to_pass` passes — these are the tests that failed before the fix;
2. every test listed in `pass_to_pass` still passes — no regressions are allowed.

The leaderboard metric is **pass@1**: each task is given exactly one attempt, and the score is the share of tasks resolved by that attempt. Additional attempts do not improve the result.

The second condition carries real weight. Some tasks list tens of thousands of `pass_to_pass` tests — `php-001` alone lists 46,118 — so a patch that turns the target tests green by breaking behaviour elsewhere scores zero on that task.

The benchmark is packaged in the [Harbor](https://github.com/laude-institute/harbor) task format. Environment images are published on Docker Hub and pinned by digest in `dataset.toml`, so nothing has to be built from source.

| | |
| :-- | :-- |
| Tasks | 49 — 18 Go, 16 Python, 15 PHP |
| Difficulty | 10 easy, 23 medium, 16 hard |
| Per-task limits | 2 CPU, 4 GB RAM, 16 GB disk, 3600 s agent, 3600 s verifier |
| Image platform | `linux/amd64` |
| Runner | Harbor 0.22.0, pinned in `requirements.txt` |
| Metric | pass@1 over all 49 tasks |
| Deliverable | `sample_submission.zip`, optionally `sample_trajectory.zip` |

---

## Task anatomy

Repository layout:

```text
SWE-MERA-CHALLENGE/
├── dataset.toml              task list with pinned image digests
├── requirements.txt          fully pinned Harbor runner environment
├── tasks/<task-id>/          49 task definitions
├── scripts/
│   └── swemera.py            scoring and packaging in one command
├── configs/
│   └── .env.example          API key template
└── example_submission/       a reference submission: submission.csv and diffs/
```

A single task looks like this:

```text
tasks/go-001/
├── instruction.md            the agent prompt: issue text, scope, completion criteria
├── task.toml                 language, difficulty, repo, base_commit, resource limits
├── environment/
│   └── Dockerfile            derives from the public image and strips fix/test artifacts
├── solution/
│   ├── fix.patch             the upstream maintainer patch, reference only
│   └── solve.sh              oracle agent: applies fix.patch
└── tests/
    ├── config.json           command_build, command_test, fail_to_pass, pass_to_pass
    ├── test.patch            tests from the upstream pull request
    ├── run_tests.py          applies the test patch, runs the suite, parses junit.xml
    ├── parse                 report parser
    └── test.sh               verifier entrypoint
```

Properties worth knowing before the first run:

| Property | Practical consequence |
| :-- | :-- |
| `/testbed` is the only writable work area | changes made outside it never reach the diff |
| Git history is truncated to a single snapshot | the upstream fix commit cannot be recovered from the repository |
| The image is stripped of `fix.patch`, `test.patch` and gold evaluation helpers | no reference solution is reachable from inside the container |
| Tests are injected only at verification time | the agent cannot read `fail_to_pass` or shape code around test names |
| The deliverable is a `git diff` taken inside `/testbed` | new files must be staged with `git add`, otherwise they are absent from the patch |
| Toolchains differ per language | Go uses `gotestsum`, PHP uses `composer install` and `phpunit`, Python uses `pip install -e .` and `pytest` |
| Results are reported through `junit.xml` | test identifiers in `config.json` match the parsed report, not raw console output |

---

## Installation

### Requirements

| Component | Version | Why |
| :-- | :-- | :-- |
| Python | `3.12` or newer | Harbor requires it; check with `python3 --version` |
| Docker | `>= 24`, daemon running | every task executes in a container |
| Git | `>= 2.30` | cloning and diff handling |
| Disk | `>= 60 GB` free | task images are large, the PHP ones especially |
| CPU | `>= 2` cores per concurrent task | the container limit is 2 |
| RAM | `>= 4 GB` per concurrent task | the container limit is 4 GB |
| Architecture | `x86_64` host, or Docker with `linux/amd64` emulation | the images are amd64-only |

### Setup

Install the runner from `requirements.txt`. It pins Harbor and every transitive dependency, so the environment is reproducible; installing `harbor` alone resolves different dependency versions and breaks in various ways.

```bash
git clone https://github.com/MERA-Evaluation/SWE-MERA-CHALLENGE.git
cd SWE-MERA-CHALLENGE

python3 --version
python3 -m venv .venv && source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

harbor --version
```

`harbor --version` must print `0.22.0`.

### Check Docker

The daemon must be running and able to execute `linux/amd64` images before the first task is launched:

```bash
docker info
docker run --rm --platform=linux/amd64 hello-world
```

### Model configuration

Harbor resolves models through LiteLLM, so a model is selected by the agent flag and the model name, and credentials come from the environment:

```bash
cp configs/.env.example .env
vim .env
```

**Fill in the key of one provider and delete the rest.** An empty variable is ignored, but a variable holding a wrong or expired key makes the run fail with `401` even when another provider is configured correctly. The `*_API_BASE` / `*_BASE_URL` lines carry the provider defaults: keep them as they are unless you route through a proxy, a regional endpoint or a local server.

Each block below is one complete, self-sufficient configuration.

**OpenRouter** — `-m openrouter/qwen/qwen3.7-flash`

```dotenv
OPENROUTER_API_KEY=sk-or-v1-...
OPENROUTER_API_BASE=https://openrouter.ai/api/v1
```

**OpenAI** — `-m openai/gpt-5.4`

```dotenv
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=https://api.openai.com/v1
```

**Anthropic** — `-m anthropic/claude-sonnet-4.6`

```dotenv
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_API_BASE=https://api.anthropic.com
```

**Gemini** — `-m gemini/gemini-3.1-pro`

```dotenv
GEMINI_API_KEY=...
```

**A local or self-hosted model** — vLLM, SGLang, TGI, llama.cpp, LM Studio, Ollama or any proxy that speaks the OpenAI protocol. Reuse the OpenAI variables and point them at your server:

```dotenv
OPENAI_API_KEY=dummy
OPENAI_BASE_URL=http://host.docker.internal:8000/v1
```

| Rule | Detail |
| :-- | :-- |
| URL shape | must end with `/v1`; do not append `/chat/completions`, the client adds the route |
| From a container | `localhost` means the container itself — use `host.docker.internal` or the host IP |
| The key | most local servers ignore it, but the client requires a non-empty value, hence `dummy` |
| Model name | pass `-m openai/<name>` where `<name>` is what the server reports: `curl $OPENAI_BASE_URL/models` |
| Endpoint | the agents use Chat Completions (`/v1/chat/completions`); a server exposing only `/v1/responses` will not work |

The same two variables cover a corporate gateway or an Azure-style proxy — only the URL changes. The file is loaded with `--env-file .env`; `.env` is git-ignored.

> [!TIP]
> Images are pulled once and cached by Docker. The first run is slow, later runs are noticeably faster. On rented hardware, warm the cache on a few tasks before launching the full sweep.

> [!NOTE]
> Verification time varies a lot between tasks. A Go task finishes in under a minute, while a large PHP task runs tens of thousands of `pass_to_pass` tests and needs tens of minutes on 2 cores. On an arm64 host the amd64 images run under emulation and everything becomes several times slower, which can push the biggest PHP tasks into the 3600 s verifier timeout; run the scoring sweep on a native `x86_64` machine.

---

## Running the benchmark

### Validate the harness first

The oracle agent applies the upstream patch, so the task must resolve and the reward must be `1`. If it does not, the problem is in the environment rather than in the model.

```bash
harbor run -p tasks -i go-001 -a oracle -o jobs/smoke --n-attempts 1 -n 1 -y
```

| Flag | Meaning |
| :-- | :-- |
| `-p, --path` | path to the task directory, here `tasks` |
| `-i, --include-task-name` | task name or glob; repeat the flag for several tasks |
| `-a, --agent` | agent to run, `oracle` for the reference patch |
| `-m, --model` | model name passed to the agent |
| `-o, --jobs-dir` | where job results are written |
| `-k, --n-attempts` | attempts per trial; the metric is pass@1, so always `1` |
| `-n, --n-concurrent` | number of concurrent trials |
| `-y` | auto-confirm prompts |

### Run your own model

The metric is pass@1, so a scoring run gives every task a single attempt. That is already the Harbor default, but pass `--n-attempts 1` explicitly so the run cannot inherit a different value from a config file or a shell alias:

```bash
harbor run \
  -p tasks \
  -a mini-swe-agent \
  -m openrouter/qwen/qwen3.7-flash \
  --env-file .env \
  -o jobs/run-001 \
  --n-attempts 1 \
  -n 2 \
  -y
```

Any Harbor agent works: `terminus-2`, `mini-swe-agent`, `swe-agent`, `openhands`, `claude-code`, `codex` and others; run `harbor run --help` for the full list, or pass an import path to your own implementation.

Choose `-n` according to the available hardware: one task takes 2 cores and 4 GB of RAM, so four in parallel already imply 8 cores and 16 GB.

### Subsets

While tuning the agent, run a small mixed-language subset — it gives a signal in minutes instead of hours.

```bash
harbor run -p tasks -i go-012 -i php-001 -i py-005 -a oracle -o jobs/run-002 --n-attempts 1 -y
```

### What the run produces

Harbor writes one job directory per run, and inside it one trial directory per attempt, named `<task-id>__<suffix>`:

```text
jobs/run-001/2026-08-21__14-44-53/
├── config.json                            the task list the job was launched with
├── lock.json                              harbor version, concurrency, resolved trials
├── result.json                            job-level stats and per-eval reward summary
├── job.log
└── go-001__cEAJUzd/
    ├── config.json                        task path, trial name, job id
    ├── lock.json                          task digest, agent, environment
    ├── result.json                        task_name, agent_info, verifier_result.rewards.reward, timings
    ├── trial.log
    ├── agent/                             whatever the agent writes: logs, trajectory, tool calls
    ├── artifacts/
    │   ├── manifest.json                  what was copied out of the container
    │   └── logs/artifacts/                everything the agent left in /logs/artifacts
    └── verifier/
        ├── apply_test_patch.log
        ├── command_build.log
        ├── command_test.log
        ├── test-stdout.txt
        ├── parse.log
        ├── parse_result.json              passed_tests, failed_tests, skipped_tests, ignored_tests
        ├── report.json                    build and test return codes, junit_found, reward
        └── reward.txt                     1 if the task is resolved, otherwise 0
```

### Where the patch comes from

The patch is produced by the harness, not by the agent. Every `tasks/*/task.toml` declares a collect hook that Harbor runs after the agent phase and before artifact collection:

```toml
[[verifier.collect]]
command = '''... git add -A ... git diff --cached --binary "$BASE" > /logs/artifacts/model_patch.diff'''
timeout_sec = 120.0
```

Harbor copies `/logs/artifacts/` to `<trial>/artifacts/logs/artifacts/`, so `model_patch.diff` is there for every task whatever agent was used — including an agent that never exports a patch, one that dies on a timeout, and the oracle.

| Property | Detail |
| :-- | :-- |
| When | after the agent, before the test patch is applied, so test files never leak into the diff |
| Baseline | the `task snapshot` root commit, so agents that commit their work are covered too |
| Contents | modified, added and deleted files, untracked ones included, binaries via `--binary` |
| Excluded | git-ignored files, `junit.xml`, `task_tests.json`, `*.orig`, `*.rej` |
| Side effects | none — a private `GIT_INDEX_FILE` keeps the agent's index and `git status` intact |
| If it fails | Harbor logs a warning in `trial.log`; `swemera.py` then refuses to build the archive |

Do not delete that hook: without it the run produces no patches and nothing can be submitted, however many tasks were solved.

Keep the job directory until the results are submitted: both archives are assembled from it.

---

## Submitting results

### Build the archives

One command scores the run and writes both archives. Point it at the timestamped job directory, the one that contains the trials:

```bash
python3 scripts/swemera.py --jobs-dir jobs/run-001/2026-08-21__14-44-53
```

It maps every trial to a task id through `result.json` (`task_name`) or the trial name, keeps the first attempt of each task, prints the report and packs `sample_submission.zip` and `sample_trajectory.zip`.

| Flag | Effect |
| :-- | :-- |
| `--score-only` | print the report, write nothing |
| `--diffs-dir DIR` | also write the diffs as plain `<task-id>.diff` files for review |
| `--json FILE` | machine-readable report for comparing runs |
| `--list-failed` | print the unresolved task ids |
| `--allow-missing` | pack even when some tasks have no patch |
| `--max-file-mb N` | skip trajectory files above N MB, 25 by default |

**The script refuses to build an incomplete archive.** If any task has no patch, it names the tasks, points at the collect hook and exits non-zero without writing anything. That is deliberate: an archive missing patches silently scores those tasks as unresolved, and the mistake is only visible on the leaderboard. Override with `--allow-missing` when you really intend to submit a partial run; the exit code stays non-zero either way, so CI cannot ignore it.

Standard library only, so any Python 3.11 or newer runs it.

### `sample_submission.zip` — what gets scored

```text
submission.csv
diffs/go-001.diff
diffs/go-002.diff
...
diffs/py-020.diff
```

`submission.csv` has exactly two columns:

```csv
task_id,diff_path
go-001,diffs/go-001.diff
go-002,diffs/go-002.diff
php-001,diffs/php-001.diff
py-001,diffs/py-001.diff
```

| Field | Requirement |
| :-- | :-- |
| `task_id` | must match a directory name under `tasks/`, for example `go-001` |
| `diff_path` | path inside the archive, one diff per task |
| diff format | unified diff applied to `/testbed` with `git apply` |
| encoding | UTF-8, LF line endings |
| missing tasks | allowed, but scored as unresolved |

### `sample_trajectory.zip` — what backs the score

This archive is the Harbor job directory as it stands on disk, nothing reshaped and nothing invented:

```text
2026-08-21__14-44-53/config.json
2026-08-21__14-44-53/lock.json
2026-08-21__14-44-53/result.json
2026-08-21__14-44-53/job.log
2026-08-21__14-44-53/go-001__cEAJUzd/result.json
2026-08-21__14-44-53/go-001__cEAJUzd/agent/
2026-08-21__14-44-53/go-001__cEAJUzd/artifacts/logs/artifacts/model_patch.diff
2026-08-21__14-44-53/go-001__cEAJUzd/verifier/report.json
2026-08-21__14-44-53/go-001__cEAJUzd/verifier/parse_result.json
...
```

The trial `result.json` records the task, the agent and its model, the reward and the timings. The `agent/` directory holds everything the agent logged, including the trajectory. The `verifier/` directory holds the build and test logs, the parsed report and the reward. Together they let us review how a patch was produced and reproduce the run. Files larger than `--max-file-mb`, 25 MB by default, are skipped.

### Reference example

`example_submission/` is a complete submission in the expected format, with placeholder patches:

```text
example_submission/
├── submission.csv            50 lines: one header plus 49 tasks
└── diffs/                    49 unified diffs, one per task
```

```bash
head -3 example_submission/submission.csv
cat example_submission/diffs/go-001.diff
```

Each patch creates a `STUB_<task-id>.txt` file: it demonstrates the format and resolves nothing. Your own archive has the same shape, with the placeholders replaced by the diffs produced by the agent.

### Pre-flight check

```bash
unzip -l sample_submission.zip
unzip -p sample_submission.zip submission.csv
```

A full run gives 50 CSV lines: one header plus one diff for each of the 49 tasks. If a diff is empty, the agent most likely worked outside `/testbed` or never staged its new files.

### Upload

Upload `sample_submission.zip`, and optionally `sample_trajectory.zip`, through the platform.

> [!IMPORTANT]
> Keep local copies of both archives. If the upload fails or the platform hits a technical problem, we will ask you to resend them, and there is no other way to restore the result.

---

## Local scoring

`scripts/swemera.py` reads `verifier/parse_result.json` from every trial and compares the passed tests against `fail_to_pass` and `pass_to_pass` from `tasks/*/tests/config.json`, applying the same rule as the platform. When the parsed report is missing, it falls back to the Harbor reward in the trial `result.json`. It reports pass@1 over the single attempt of each task; if a task happens to have several trials in the job, only the first one counts.

Harbor also writes a reward mean into `jobs/<timestamp>/result.json`, but it divides by the trials that actually ran. The leaderboard divides by all 49 tasks, which is what this script reports — hence the separate `evaluated` and `patches` counters.

```bash
python3 scripts/swemera.py --jobs-dir jobs/run-001/2026-08-21__14-44-53 --score-only
python3 scripts/swemera.py --jobs-dir jobs/run-001/2026-08-21__14-44-53 --score-only --list-failed --json metrics.json
```

```text
  pass@1 34/49  69.39%   evaluated 49/49   patches 49/49
```

| Row or flag | Meaning |
| :-- | :-- |
| `pass@1` | the leaderboard metric: share of the 49 tasks resolved on their single attempt |
| `evaluated` | how many tasks actually reached the verifier |
| `patches` | how many tasks produced a diff; anything below `evaluated` means the collect hook failed |
| gap between `pass@1` and `evaluated` | part of the run died on a timeout or an infrastructure error and should be repeated |
| `--list-failed` | prints the unresolved task ids |
| `--json` | writes a machine-readable report for comparing runs |

---

## Rules and penalties

> [!WARNING]
> **Submissions matching the gold solution will be penalised.** The gold patches under `tasks/*/solution/` exist so that the oracle agent can validate the harness. Copying `fix.patch`, rewording it cosmetically or reusing it in any other way is treated as a violation and may invalidate the result.

In addition:

- submit only patches produced by the agent during the run;
- do not modify `tasks/*/tests/` and do not tailor code to test names or structure;
- do not disable, delete or rewrite tests inside `/testbed`;
- retain the trajectories — without them there is no way to confirm that a patch came from an agent.

---

## Troubleshooting

| Symptom | Cause and fix |
| :-- | :-- |
| `harbor --version` prints something other than `0.22.0` | the environment was not installed from `requirements.txt`; recreate the virtualenv |
| `no match for platform in manifest` | the Docker host cannot run `linux/amd64`; enable emulation or use an x86_64 machine |
| `range of CPUs is from 0.01 to N` | Docker has fewer cores available than the task requests; give Docker at least 2 cores per concurrent task |
| the oracle run does not end with reward `1` | environment or Docker issue: check that the daemon is running and that disk space is sufficient |
| `swemera.py` refuses to pack | some tasks produced no diff; the listed trials' `trial.log` shows why the collect hook failed |
| a diff comes out empty | the agent changed nothing, or it worked outside `/testbed` |
| `swemera.py` sees no trials | `--jobs-dir` must point at the timestamped job directory that contains the `<task-id>__<suffix>` trials |
| `pass@1` is far below expectation | `pass_to_pass` regressions; inspect the verifier logs under `jobs/` |
| tasks fail with timeouts | lower `-n`, the machine lacks CPU or memory |
| large gap between `evaluated` and 49 | some tasks never reached the verifier; rerun them separately |
| `submission.csv` has fewer than 50 lines | tasks are missing from the archive and will be scored as unresolved |
