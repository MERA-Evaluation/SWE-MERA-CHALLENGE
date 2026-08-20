<div align="center">

# SWE-MERA-CHALLENGE

**49 issue-resolving tasks built from real open-source bug fixes.**

<p>
  <img alt="tasks" src="https://img.shields.io/badge/tasks-49-1f6feb?style=flat-square&labelColor=0d1117">
  <img alt="languages" src="https://img.shields.io/badge/Go%2018%20·%20Python%2016%20·%20PHP%2015-24292f?style=flat-square&labelColor=0d1117">
  <img alt="runner" src="https://img.shields.io/badge/runner-Harbor-6e40c9?style=flat-square&labelColor=0d1117">
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

The benchmark is packaged in the [Harbor](https://github.com/laude-institute/harbor) task format. Environment images are published on Docker Hub and pinned by digest in `dataset.toml`, so nothing has to be built locally.

| | |
| :-- | :-- |
| Tasks | 49 — 18 Go, 16 Python, 15 PHP |
| Difficulty | 10 easy, 23 medium, 16 hard |
| Per-task limits | 16 CPU, 50 GB RAM, 16 GB disk, 3600 s agent, 3600 s verifier |
| Metric | pass@1 over all 49 tasks |
| Deliverable | `sample_submission.zip`, optionally `sample_trajectory.zip` |

---

## Task anatomy

Repository layout:

```text
SWE-MERA-CHALLENGE/
├── dataset.toml              task list with pinned image digests
├── tasks/<task-id>/          49 task definitions
├── scripts/
│   ├── score.py              local scoring
│   └── collect.py            builds the submission and trajectory archives
├── configs/
│   ├── models.example.toml   model profiles for hosted APIs and self-hosted endpoints
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
| Python | `>= 3.11` | Harbor CLI and the repository scripts |
| Docker | `>= 24`, daemon running | every task executes in a container |
| Git | `>= 2.30` | cloning and diff handling |
| Disk | `>= 60 GB` free | task images are large, the PHP ones especially |
| CPU | `>= 2` cores per concurrent task | the container limit is 16 |
| RAM | `>= 4 GB` per concurrent task | the container limit is 50 GB |

### Setup

```bash
git clone https://github.com/MERA-Evaluation/SWE-MERA-CHALLENGE.git
cd SWE-MERA-CHALLENGE

python3 -m venv .venv && source .venv/bin/activate
pip install --upgrade pip
pip install harbor-cli

harbor --version
docker info
```

### Model configuration

```bash
cp configs/.env.example .env
cp configs/models.example.toml configs/models.toml
$EDITOR .env configs/models.toml
set -a && source .env && set +a
```

`configs/models.example.toml` ships two families of profiles:

- **Hosted APIs** — `openrouter`, `openai`, `anthropic`, `azure`.
- **Self-hosted endpoints** — `openai_compatible`, `vllm`, `ollama`. Any server that speaks the OpenAI-compatible protocol works: vLLM, SGLang, TGI, LM Studio, llama.cpp server and others. OpenRouter is not required.

To point the run at your own deployment, set the base URL, the model name and the environment variable that holds the key:

```toml
[profiles.vllm]
provider = "openai"
model = "Qwen/Qwen3-32B"
base_url = "http://gpu-node:8000/v1"
api_key_env = "VLLM_API_KEY"
temperature = 0.0
max_tokens = 16384
max_steps = 80
```

Keys live only in `.env`, which is git-ignored together with `configs/models.toml` and the generated archives.

> [!TIP]
> Images are pulled once and cached by Docker. The first run is slow, later runs are noticeably faster. On rented hardware, warm the cache on a few tasks before launching the full sweep.

---

## Running the benchmark

### Validate the harness first

The oracle agent applies the upstream patch, so the task must resolve. If it does not, the problem is in the environment rather than in the model.

```bash
harbor run \
  --tasks-dir tasks \
  --task-ids go-001 \
  --agent oracle \
  --jobs-dir jobs/smoke
```

### Run your own model

The metric is pass@1, so a scoring run gives every task a single attempt:

```bash
harbor run \
  --tasks-dir tasks \
  --agent-config configs/models.toml \
  --agent-profile openai_compatible \
  --n-concurrent 2 \
  --jobs-dir jobs/run-001
```

Choose `--n-concurrent` according to the available hardware: one task may take 2 cores and 4 GB of RAM, so two in parallel already imply 4 cores and 8 GB.

### Subsets

While tuning the agent, run a small mixed-language subset — it gives a signal in minutes instead of hours.

```bash
harbor run --tasks-dir tasks --task-ids go-012,php-001,py-005 --jobs-dir jobs/run-002
```

### What the run produces

Harbor writes one job directory and, inside it, one trial directory per attempt, named `<task-id>__<suffix>`:

```text
jobs/run-001/
├── config.json                            the task list the job was launched with
├── lock.json                              harbor version, concurrency, resolved trials
├── result.json                            job-level stats and per-eval reward summary
├── job.log
└── go-001__mepGVhf/
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

> [!IMPORTANT]
> Harbor does not extract the patch by itself. Make the agent write its final diff to `/logs/artifacts/model_patch.diff` inside the container — Harbor copies that directory to `<trial>/artifacts/logs/artifacts/`, and `collect.py` picks the file up from there.
>
> ```bash
> git -C /testbed add -A
> git -C /testbed diff --cached > /logs/artifacts/model_patch.diff
> ```

Keep the job directory until the results are submitted: both archives are assembled from it.

---

## Submitting results

### Build the archives

```bash
python3 scripts/collect.py --jobs-dir jobs/run-001
```

The script walks the job directory, maps every trial to a task id through `result.json` (`task_name`) or the trial name, takes the first attempt of each task and writes two archives into the current directory. To build only one of them:

```bash
python3 scripts/collect.py --jobs-dir jobs/run-001 --only submission
python3 scripts/collect.py --jobs-dir jobs/run-001 --only trajectory
```

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
run-001/config.json
run-001/lock.json
run-001/result.json
run-001/job.log
run-001/go-001__mepGVhf/result.json
run-001/go-001__mepGVhf/agent/trajectory.json
run-001/go-001__mepGVhf/artifacts/logs/artifacts/model_patch.diff
run-001/go-001__mepGVhf/verifier/report.json
run-001/go-001__mepGVhf/verifier/parse_result.json
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

`scripts/score.py` reads `verifier/parse_result.json` from every trial in the job and compares the passed tests against `fail_to_pass` and `pass_to_pass` from `tasks/*/tests/config.json`, applying the same rule as the platform. When the parsed report is missing, it falls back to the Harbor reward in the trial `result.json`. It reports pass@1 over the single attempt of each task; if a task happens to have several trials in the job, only the first one counts.

```bash
python3 scripts/score.py --jobs-dir jobs/run-001
python3 scripts/score.py --jobs-dir jobs/run-001 --list-failed --json metrics.json
```

```text
  SWE-MERA-CHALLENGE
  ──────────────────────────────────────────────────────────
  pass@1      ████████████████·········   34 / 49    69.39 %
  evaluated   ████████████████████████    49 / 49
  ──────────────────────────────────────────────────────────
  language
    go        █████████████████·······    13 / 18    72.22 %
    php       ████████████████········    10 / 15    66.67 %
    python    █████████████████·······    11 / 16    68.75 %
  ──────────────────────────────────────────────────────────
  difficulty
    easy      ██████████████████████··     9 / 10    90.00 %
    medium    ██████████████████······    17 / 23    73.91 %
    hard      ████████████············     8 / 16    50.00 %
  ──────────────────────────────────────────────────────────
```

| Row or flag | Meaning |
| :-- | :-- |
| `pass@1` | the leaderboard metric: share of the 49 tasks resolved on their single attempt |
| `evaluated` | how many tasks actually reached the verifier |
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
| the oracle run does not resolve a task | environment or Docker issue: check that the daemon is running and that disk space is sufficient |
| `collect.py` reports `no patches found` | wrong `--jobs-dir`, or the agent never wrote its diff to `/logs/artifacts/` |
| a diff comes out empty | the edits were made outside `/testbed`, or new files were never staged in git |
| `score.py` sees no trials | `--jobs-dir` points above or below the job directory; it must contain the `<task-id>__<suffix>` trials |
| `pass@1` is far below expectation | `pass_to_pass` regressions; inspect the verifier logs under `jobs/` |
| tasks fail with timeouts | lower `--n-concurrent`, the machine lacks CPU or memory |
| large gap between `evaluated` and 49 | some tasks never reached the verifier; rerun them separately |
| `submission.csv` has fewer than 50 lines | tasks are missing from the archive and will be scored as unresolved |
