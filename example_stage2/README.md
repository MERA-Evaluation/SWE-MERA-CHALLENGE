# SWE-MERA Stage 2 submission

Participants provide:

- `submission.yaml` with `username`, `agent`, and `model`;
- the inference build context in `inference/`;
- `custom_agent/` when `agent: custom_agent` is selected.

`run.sh`, `private_run.sh`, and `inference/test.sh` are trusted organizer files.
The official evaluator uses its own copies of these scripts.

`run.sh` builds and starts the inference image, validates its API, and launches
Harbor. `private_run.sh` supplies private evaluation paths and removes the
submission's container and image before and after the run.
