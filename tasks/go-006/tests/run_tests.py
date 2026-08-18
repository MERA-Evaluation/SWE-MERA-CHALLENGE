#!/usr/bin/env python3
import argparse
import json
import os
import shutil
import stat
import subprocess
import sys


REPO_DIR = "/testbed"
JUNIT_PATH = "/testbed/junit.xml"
PARSE_BIN = "/tests/parse"
TEST_PATCH_PATH = "/tests/test.patch"
TASK_TESTS_PATH = "/tests/task_tests.json"


def read_config(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def write_text(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def run_shell(command, cwd, log_path):
    with open(log_path, "w", encoding="utf-8") as log:
        proc = subprocess.run(
            command,
            cwd=cwd,
            shell=True,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
    return proc.returncode


def ensure_executable(path, log_dir):
    try:
        st = os.stat(path)
        os.chmod(path, st.st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        if os.access(path, os.X_OK):
            return path
    except OSError:
        pass
    dst = os.path.join(log_dir, os.path.basename(path))
    shutil.copyfile(path, dst)
    os.chmod(dst, 0o755)
    return dst


def ensure_git_safe(cwd):

    subprocess.run(
        ["git", "config", "--global", "--add", "safe.directory", "*"],
        cwd=cwd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def apply_test_patch(patch_path, cwd, log_path):
    ensure_git_safe(cwd)
    attempts = [
        "git apply --3way --ignore-space-change --whitespace=nowarn " + patch_path,
        "git apply --ignore-space-change --whitespace=nowarn " + patch_path,
        "patch -p1 --fuzz=3 < " + patch_path,
    ]
    rc = 1
    with open(log_path, "w", encoding="utf-8") as log:
        for command in attempts:
            log.write("\n$ " + command + "\n")
            log.flush()
            proc = subprocess.run(
                command,
                cwd=cwd,
                shell=True,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
            rc = proc.returncode
            if rc == 0:
                break
    return rc



def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--log-dir", required=True)
    args = parser.parse_args()

    os.makedirs(args.log_dir, exist_ok=True)
    config = read_config(args.config)

    command_test = config["command_test"]
    command_build = config.get("command_build")
    fail_to_pass = config.get("fail_to_pass", [])
    pass_to_pass = config.get("pass_to_pass", [])


    task_tests = {"tests": {"pass_to_pass": pass_to_pass, "fail_to_pass": fail_to_pass}}
    write_json(TASK_TESTS_PATH, task_tests)

    report = {
        "test_patch_applied": False,
        "test_patch_rc": None,
        "command_build": command_build,
        "command_build_rc": None,
        "command_test": command_test,
        "command_test_rc": None,
        "junit_found": False,
        "parse_rc": None,
        "reward": 0,
    }


    reward_path = os.path.join(args.log_dir, "reward.txt")
    report_path = os.path.join(args.log_dir, "report.json")

    if os.path.exists(TEST_PATCH_PATH):
        patch_log = os.path.join(args.log_dir, "apply_test_patch.log")
        rc = apply_test_patch(TEST_PATCH_PATH, REPO_DIR, patch_log)
        report["test_patch_applied"] = rc == 0
        report["test_patch_rc"] = rc
        if rc != 0:
            write_text(reward_path, "0")
            write_json(report_path, report)
            print("FAIL: test patch did not apply")
            sys.exit(0)

    if command_build and command_build.strip():
        build_log = os.path.join(args.log_dir, "command_build.log")
        report["command_build_rc"] = run_shell(command_build, REPO_DIR, build_log)

    test_log = os.path.join(args.log_dir, "command_test.log")
    report["command_test_rc"] = run_shell(command_test, REPO_DIR, test_log)


    if not os.path.exists(JUNIT_PATH):
        write_text(reward_path, "0")
        write_json(report_path, report)
        print("FAIL: junit report not found at " + JUNIT_PATH)
        sys.exit(0)

    report["junit_found"] = True
    parse_out = os.path.join(args.log_dir, "parse_result.json")
    parse_log = os.path.join(args.log_dir, "parse.log")
    parse_bin = ensure_executable(PARSE_BIN, args.log_dir)
    with open(parse_log, "w", encoding="utf-8") as log:
        proc = subprocess.run(
            [parse_bin, JUNIT_PATH, TASK_TESTS_PATH, parse_out],

            stdout=log,
            stderr=subprocess.STDOUT,
        )
    report["parse_rc"] = proc.returncode
    report["reward"] = 1 if proc.returncode == 0 else 0

    write_text(reward_path, str(report["reward"]))
    write_json(report_path, report)
    print("PASS" if report["reward"] == 1 else "FAIL")
    sys.exit(0)


if __name__ == "__main__":
    main()
