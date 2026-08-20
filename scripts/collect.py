#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
import zipfile
from pathlib import Path

TASK_ID_RE = re.compile(r"(go|php|py)-\d{3}")

DIFF_NAMES = (
    "model_patch.diff",
    "model_patch.patch",
    "patch.diff",
    "solution.diff",
    "agent_patch.diff",
    "output.patch",
)

DIFF_DIRS = ("artifacts", "agent")

SKIP_PARTS = {"__pycache__", ".git", "node_modules"}


def task_id_of(trial_dir: Path) -> str | None:
    result = trial_dir / "result.json"
    if result.is_file():
        try:
            data = json.loads(result.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            data = {}
        name = str(data.get("task_name") or "")
        match = TASK_ID_RE.search(name)
        if match:
            return match.group(0)
    match = TASK_ID_RE.search(trial_dir.name)
    return match.group(0) if match else None


def reward_of(trial_dir: Path) -> float:
    result = trial_dir / "result.json"
    if result.is_file():
        try:
            data = json.loads(result.read_text(encoding="utf-8"))
            rewards = data.get("verifier_result") or {}
            value = (rewards.get("rewards") or {}).get("reward")
            if isinstance(value, (int, float)):
                return float(value)
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass
    reward_file = trial_dir / "verifier" / "reward.txt"
    if reward_file.is_file():
        try:
            return float(reward_file.read_text(encoding="utf-8").strip() or 0)
        except ValueError:
            return 0.0
    return 0.0


def iter_trials(jobs_dir: Path):
    for path in sorted(jobs_dir.rglob("*")):
        if not path.is_dir() or not (path / "result.json").is_file():
            continue
        if not (path / "verifier").exists() and not (path / "agent").exists():
            continue
        task_id = task_id_of(path)
        if task_id:
            yield task_id, path


def select_trials(jobs_dir: Path) -> dict[str, Path]:
    first: dict[str, Path] = {}
    for task_id, trial_dir in iter_trials(jobs_dir):
        first.setdefault(task_id, trial_dir)
    return {task_id: first[task_id] for task_id in sorted(first)}


def find_diff(trial_dir: Path) -> Path | None:
    roots = [trial_dir / name for name in DIFF_DIRS if (trial_dir / name).is_dir()]
    roots.append(trial_dir)
    for root in roots:
        for name in DIFF_NAMES:
            for hit in sorted(root.rglob(name)):
                if hit.is_file() and hit.stat().st_size > 0:
                    return hit
    pool = [
        p
        for p in sorted(trial_dir.rglob("*"))
        if p.is_file()
        and p.suffix in {".diff", ".patch"}
        and "test" not in p.name.lower()
        and not SKIP_PARTS.intersection(p.parts)
        and p.stat().st_size > 0
    ]
    if pool:
        pool.sort(key=lambda p: (-p.stat().st_size, str(p)))
        return pool[0]
    return None


def build_submission(jobs_dir: Path, trials: dict[str, Path], out: Path) -> int:
    rows: list[tuple[str, str]] = []
    files: list[tuple[str, bytes]] = []
    missing: list[str] = []

    for task_id, trial_dir in trials.items():
        diff = find_diff(trial_dir)
        if diff is None:
            missing.append(task_id)
            continue
        arcname = f"diffs/{task_id}.diff"
        files.append((arcname, diff.read_bytes()))
        rows.append((task_id, arcname))

    if not rows:
        print("no patches found in jobs dir", file=sys.stderr)
        return 0

    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(["task_id", "diff_path"])
    writer.writerows(rows)

    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("submission.csv", buf.getvalue())
        for arcname, data in files:
            zf.writestr(arcname, data)

    print(f"submission   {len(rows)} tasks   ->  {out}")
    if missing:
        print(f"no patch for: {', '.join(missing)}", file=sys.stderr)
    return len(rows)


def build_trajectory(jobs_dir: Path, out: Path, limit_mb: int) -> int:
    limit_bytes = limit_mb * 1024 * 1024
    root = jobs_dir.resolve()
    top = root.name
    files: list[tuple[str, Path]] = []
    skipped = 0

    for path in sorted(root.rglob("*")):
        if not path.is_file() or SKIP_PARTS.intersection(path.parts):
            continue
        if path.stat().st_size > limit_bytes:
            skipped += 1
            continue
        files.append((f"{top}/{path.relative_to(root).as_posix()}", path))

    if not files:
        print("nothing to collect in jobs dir", file=sys.stderr)
        return 0

    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for arcname, path in files:
            zf.write(path, arcname)

    print(f"trajectory   {len(files)} files   ->  {out}")
    if skipped:
        print(f"skipped {skipped} files over {limit_mb} MB", file=sys.stderr)
    return len(files)


def main() -> int:
    parser = argparse.ArgumentParser(prog="collect.py")
    parser.add_argument("--jobs-dir", required=True)
    parser.add_argument("--submission-out", default="sample_submission.zip")
    parser.add_argument("--trajectory-out", default="sample_trajectory.zip")
    parser.add_argument("--max-file-mb", type=int, default=25)
    parser.add_argument("--only", choices=["submission", "trajectory"])
    args = parser.parse_args()

    jobs_dir = Path(args.jobs_dir)
    if not jobs_dir.is_dir():
        print(f"jobs dir not found: {jobs_dir}", file=sys.stderr)
        return 2

    packed = 0
    if args.only != "trajectory":
        packed += build_submission(jobs_dir, select_trials(jobs_dir), Path(args.submission_out))
    if args.only != "submission":
        packed += build_trajectory(jobs_dir, Path(args.trajectory_out), args.max_file_mb)

    return 0 if packed else 1


if __name__ == "__main__":
    raise SystemExit(main())
