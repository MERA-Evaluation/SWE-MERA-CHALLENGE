#!/usr/bin/env python3
import argparse, csv, io, json, re, sys, zipfile
from pathlib import Path

ID = re.compile(r"(go|php|py)-\d{3}")


def js(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def solved(trial, tasks, tid):
    cfg = js(tasks / tid / "tests" / "config.json")
    want = set(cfg.get("fail_to_pass") or []) | set(cfg.get("pass_to_pass") or [])
    got = js(trial / "verifier" / "parse_result.json").get("passed_tests")
    if isinstance(got, list) and want:
        return want <= {str(t) for t in got}
    reward = ((js(trial / "result.json").get("verifier_result") or {}).get("rewards") or {}).get("reward")
    if reward is None:
        reward = js(trial / "verifier" / "report.json").get("reward", 0)
    try:
        return float(reward) >= 1
    except (TypeError, ValueError):
        return False


def patch_of(trial):
    named = trial / "artifacts/logs/artifacts/model_patch.diff"
    found = [named, *sorted(trial.rglob("*.diff")), *sorted(trial.rglob("*.patch"))]
    return next((p for p in found if p.is_file() and p.stat().st_size and "test" not in p.name.lower()), None)


def main():
    ap = argparse.ArgumentParser(prog="swemera.py")
    ap.add_argument("--jobs-dir", required=True)
    ap.add_argument("--tasks-dir", default="tasks")
    ap.add_argument("--submission-out", default="sample_submission.zip")
    ap.add_argument("--trajectory-out", default="sample_trajectory.zip")
    ap.add_argument("--diffs-dir")
    ap.add_argument("--json")
    ap.add_argument("--max-file-mb", type=int, default=25)
    for flag in ("--score-only", "--allow-missing", "--list-failed"):
        ap.add_argument(flag, action="store_true")
    args = ap.parse_args()

    jobs, tasks = Path(args.jobs_dir), Path(args.tasks_dir)
    ids = sorted(p.name for p in tasks.iterdir() if ID.fullmatch(p.name)) if tasks.is_dir() else []
    if not jobs.is_dir() or not ids:
        print(f"not a job dir or no tasks: {jobs} {tasks}", file=sys.stderr)
        return 2

    trials = {}
    for path in sorted(jobs.rglob("*")):
        if path.is_dir() and (path / "result.json").is_file():
            hit = ID.search(str(js(path / "result.json").get("task_name") or "")) or ID.search(path.name)
            if hit and hit.group() in ids:
                trials.setdefault(hit.group(), path)

    good = {t for t in trials if solved(trials[t], tasks, t)}
    patches = {t: p for t in sorted(trials) if (p := patch_of(trials[t]))}
    missing = [t for t in ids if t not in patches]
    total = len(ids)

    print(f"  pass@1 {len(good)}/{total}  {100 * len(good) / total:.2f}%   "
          f"evaluated {len(trials)}/{total}   patches {len(patches)}/{total}")
    if args.list_failed:
        print("  unresolved:", " ".join(t for t in ids if t not in good) or "none")
    if args.json:
        Path(args.json).write_text(json.dumps({
            "total": total, "pass_at_1": len(good), "pass_at_1_rate": round(len(good) / total, 6),
            "evaluated": len(trials), "patches": len(patches), "missing_patches": missing,
            "tasks": {t: t in good for t in ids}}, indent=2, sort_keys=True), encoding="utf-8")
    if args.diffs_dir:
        out = Path(args.diffs_dir)
        out.mkdir(parents=True, exist_ok=True)
        for tid, src in patches.items():
            (out / f"{tid}.diff").write_bytes(src.read_bytes())
    if missing:
        print(f"  no patch for {len(missing)}: {' '.join(missing)}\n"
              "  the [[verifier.collect]] hook in task.toml writes it, see trial.log", file=sys.stderr)
    if args.score_only:
        return bool(missing)
    if not patches or (missing and not args.allow_missing):
        print("  refusing to pack an incomplete submission, --allow-missing overrides", file=sys.stderr)
        return 1

    rows = io.StringIO()
    csv.writer(rows, lineterminator="\n").writerows(
        [["task_id", "diff_path"], *([t, f"diffs/{t}.diff"] for t in sorted(patches))])
    with zipfile.ZipFile(args.submission_out, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("submission.csv", rows.getvalue())
        for tid, src in sorted(patches.items()):
            zf.writestr(f"diffs/{tid}.diff", src.read_bytes())
    root = jobs.resolve()
    with zipfile.ZipFile(args.trajectory_out, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(root.rglob("*")):
            if p.is_file() and p.stat().st_size <= args.max_file_mb << 20 and "__pycache__" not in p.parts:
                zf.write(p, f"{root.name}/{p.relative_to(root).as_posix()}")
    print(f"  packed {len(patches)} diffs -> {args.submission_out} + {args.trajectory_out}")
    return bool(missing)


if __name__ == "__main__":
    raise SystemExit(main())
