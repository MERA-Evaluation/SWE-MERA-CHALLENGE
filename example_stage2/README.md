# SWE-MERA Stage 2 submission

Participants provide:

- `submission.yaml` with only `agent` and `model`;
- the inference build context in `inference/`;
- `custom_agent/` when `agent: custom_agent` is selected.

`run.sh` and `inference/test.sh` are trusted organizer files.
The official evaluator always uses its own copies of these scripts and ignores
copies from the uploaded ZIP.

`run.sh` validates the submission, builds and starts the inference image, checks
its API, and launches Harbor. It removes this run's container and image before
starting and on exit, including failure. The runner preserves the exit code of
the failed stage. Do not run concurrent submissions with the same username.

The inference `docker build` has a fixed six-hour limit (`BUILD_TIMEOUT_SEC=21600`).
GNU `timeout` (or `gtimeout` on macOS) sends SIGTERM when that limit expires and
SIGKILL after a further 60 seconds if the build command has not exited. A timeout
stops the run before inference or Harbor starts, prints an error, and triggers
cleanup. The runner returns 124 for a normal timeout or 137 for forced killing.
This limit is independent of model startup and task timeouts in `task.toml`.

From the repository root, run the public tasks locally with:

```bash
./example_stage2/run.sh --username user_id
```

`--username` is mandatory and names Docker resources and the default output
directory. It is not an authentication credential or a field in the uploaded
YAML. Use 1-64 lowercase letters, digits, `.`, `_` or `-`, starting with a
letter or digit. The ODS evaluator supplies a name derived from the submission
ID automatically. An old `username` field in YAML is rejected.

To override paths or concurrency:

```bash
SWE_MERA_TASKS_DIR="$PWD/tasks" \
SWE_MERA_JOBS_DIR="$PWD/jobs/stage2-local" \
SWE_MERA_N_CONCURRENT=2 \
./example_stage2/run.sh --username user_id
```

Without overrides, tasks come from `<project>/tasks` and results go to
`<project>/jobs/stage2/<username>`. Private evaluation must supply its task
directory. The runner requires the project's `.venv/bin/python` and
`.venv/bin/harbor` and calls Harbor directly.

The inference API is published on `127.0.0.1:8000` by default. The organizer
exposes three GPUs and runs Harbor with 10 concurrent tasks by default. The
bundled `Qwen/Qwen3.5-9B` example serves `qwen35-9b-chat` using three data-parallel
replicas and `--max-num-seqs 512`. The agent timeout multiplier is 1; a task with
a 3600-second agent limit therefore gets 3600 seconds. The verifier timeout is
unchanged.

`custom_agent` is imported by the Harbor runner; only its tool commands execute
inside the no-internet task container. Production evaluation must therefore run
participant agents on an isolated worker without ODS credentials.
