#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

TASK_DIR_RE = re.compile(r"^(go|php|py)-\d{3}$")
TASK_ID_RE = re.compile(r"(go|php|py)-\d{3}")
META_RE = re.compile(r'\s*([A-Za-z_]+)\s*=\s*"([^"]*)"\s*$')

LANG_ORDER = ["go", "php", "python", "py"]
DIFF_ORDER = ["easy", "medium", "hard"]


def read_meta(tasks_dir: Path) -> dict[str, dict[str, str]]:
    meta: dict[str, dict[str, str]] = {}
    for task_dir in sorted(tasks_dir.iterdir()):
        toml = task_dir / "task.toml"
        if not TASK_DIR_RE.match(task_dir.name) or not toml.is_file():
            continue
        fields: dict[str, str] = {}
        for line in toml.read_text(encoding="utf-8").splitlines():
            m = META_RE.match(line)
            if m and m.group(1) in {"language", "difficulty"} and m.group(1) not in fields:
                fields[m.group(1)] = m.group(2)
        meta[task_dir.name] = fields
    return meta


def read_expectations(tasks_dir: Path, task_id: str) -> tuple[set[str], set[str]]:
    config = tasks_dir / task_id / "tests" / "config.json"
    if not config.is_file():
        return set(), set()
    data = json.loads(config.read_text(encoding="utf-8"))
    return set(data.get("fail_to_pass", [])), set(data.get("pass_to_pass", []))


def load_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def task_id_of(trial_dir: Path) -> str | None:
    name = str(load_json(trial_dir / "result.json").get("task_name") or "")
    match = TASK_ID_RE.search(name) or TASK_ID_RE.search(trial_dir.name)
    return match.group(0) if match else None


def iter_trials(jobs_dir: Path):
    for path in sorted(jobs_dir.rglob("*")):
        if not path.is_dir() or not (path / "result.json").is_file():
            continue
        if not (path / "verifier").exists() and not (path / "agent").exists():
            continue
        task_id = task_id_of(path)
        if task_id:
            yield task_id, path


def reward_of(trial_dir: Path) -> float | None:
    rewards = load_json(trial_dir / "result.json").get("verifier_result") or {}
    value = (rewards.get("rewards") or {}).get("reward")
    if isinstance(value, (int, float)):
        return float(value)
    reward_file = trial_dir / "verifier" / "reward.txt"
    if reward_file.is_file():
        try:
            return float(reward_file.read_text(encoding="utf-8").strip() or 0)
        except ValueError:
            return 0.0
    return None


def is_resolved(trial_dir: Path, f2p: set[str], p2p: set[str]) -> bool:
    parsed = load_json(trial_dir / "verifier" / "parse_result.json")
    passed = parsed.get("passed_tests")
    if isinstance(passed, list) and (f2p or p2p):
        names = {str(t) for t in passed}
        return f2p.issubset(names) and p2p.issubset(names)
    reward = reward_of(trial_dir)
    return reward is not None and reward >= 1.0


def bar(part: float, total: float, width: int = 24) -> str:
    filled = round(width * part / total) if total else 0
    return "█" * filled + "·" * (width - filled)


def pct(part: float, total: float) -> float:
    return (100.0 * part / total) if total else 0.0


def order_key(dimension: str, key: str) -> tuple[int, str]:
    table = LANG_ORDER if dimension == "language" else DIFF_ORDER
    return (table.index(key) if key in table else len(table), key)


def main() -> int:
    parser = argparse.ArgumentParser(prog="score.py")
    parser.add_argument("--jobs-dir", required=True)
    parser.add_argument("--tasks-dir", default="tasks")
    parser.add_argument("--json")
    parser.add_argument("--list-failed", action="store_true")
    args = parser.parse_args()

    jobs_dir = Path(args.jobs_dir)
    tasks_dir = Path(args.tasks_dir)
    if not jobs_dir.is_dir():
        print(f"jobs dir not found: {jobs_dir}", file=sys.stderr)
        return 2
    if not tasks_dir.is_dir():
        print(f"tasks dir not found: {tasks_dir}", file=sys.stderr)
        return 2

    meta = read_meta(tasks_dir)
    attempts: dict[str, list[bool]] = {task_id: [] for task_id in meta}

    for task_id, trial_dir in iter_trials(jobs_dir):
        if task_id not in attempts:
            continue
        f2p, p2p = read_expectations(tasks_dir, task_id)
        attempts[task_id].append(is_resolved(trial_dir, f2p, p2p))

    total = len(meta)
    evaluated = [t for t, runs in attempts.items() if runs]
    resolved = {t: bool(runs) and runs[0] for t, runs in attempts.items()}
    pass_at_1 = sum(1 for ok in resolved.values() if ok)
    extra = sorted(t for t, runs in attempts.items() if len(runs) > 1)

    print()
    print("  SWE-MERA-CHALLENGE")
    print("  " + "─" * 58)
    print(f"  {'pass@1':<12}{bar(pass_at_1, total)}  {pass_at_1:>3} / {total:<3}  {pct(pass_at_1, total):6.2f} %")
    print(f"  {'evaluated':<12}{bar(len(evaluated), total)}  {len(evaluated):>3} / {total:<3}")
    print("  " + "─" * 58)

    groups: dict[str, dict[str, list[int]]] = {}
    for dimension in ("language", "difficulty"):
        buckets: dict[str, list[int]] = {}
        for task_id, fields in meta.items():
            key = fields.get(dimension, "unknown")
            bucket = buckets.setdefault(key, [0, 0])
            bucket[1] += 1
            if resolved[task_id]:
                bucket[0] += 1
        groups[dimension] = buckets
        print(f"  {dimension}")
        for key in sorted(buckets, key=lambda k: order_key(dimension, k)):
            part, whole = buckets[key]
            print(f"    {key:<10}{bar(part, whole)}  {part:>3} / {whole:<3}  {pct(part, whole):6.2f} %")
        print("  " + "─" * 58)

    if args.list_failed:
        failed = sorted(t for t, ok in resolved.items() if not ok)
        if failed:
            print("  unresolved")
            for i in range(0, len(failed), 8):
                print("    " + "  ".join(failed[i : i + 8]))
            print("  " + "─" * 58)

    if extra:
        print("  more than one attempt, only the first one counts:", file=sys.stderr)
        print("    " + "  ".join(extra), file=sys.stderr)

    if args.json:
        report = {
            "total": total,
            "evaluated": len(evaluated),
            "pass_at_1": pass_at_1,
            "pass_at_1_rate": round(pass_at_1 / total, 6) if total else 0.0,
            "tasks": resolved,
            "groups": {
                dim: {k: {"resolved": v[0], "total": v[1]} for k, v in buckets.items()}
                for dim, buckets in groups.items()
            },
        }
        Path(args.json).write_text(
            json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8"
        )
        print(f"  report      {args.json}")
        print("  " + "─" * 58)

    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
