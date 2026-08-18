#!/bin/bash
set -euo pipefail

REPO_DIR="/testbed"
cd "$REPO_DIR"

git config --global --add safe.directory '*' 2>/dev/null || true

apply_patch() {
    local patch_file="$1"
    if git apply --3way --ignore-space-change --whitespace=nowarn "$patch_file"; then
        return 0
    fi
    echo "git apply --3way failed, retrying with git apply (no 3way)..."
    if git apply --ignore-space-change --whitespace=nowarn "$patch_file"; then
        return 0
    fi
    echo "git apply failed, falling back to patch -p1..."
    patch -p1 --fuzz=3 < "$patch_file"
}

echo "Applying oracle patch..."
if [ -f /solution/fix.patch ]; then
    apply_patch /solution/fix.patch
    echo "Oracle patch applied."

    git add -A
    git -c user.name="Reference" -c user.email="noreply@example.com" \
        commit -m "Apply oracle fix patch" --no-verify || true
    echo "Changes committed to git."
else
    echo "Missing /solution/fix.patch"
    exit 1
fi
