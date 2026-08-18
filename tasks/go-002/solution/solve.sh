#!/bin/bash
# Harbor oracle solution: apply the gold fix patch.
set -euo pipefail

REPO_DIR="/testbed"
cd "$REPO_DIR"

# Harbor may run this script as a different user than the one that built the
# image (where safe.directory was configured for root). Disable the ownership
# check so git operations always work regardless of the effective user.
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

    # Commit so git status stays clean (some tests depend on it).
    git add -A
    git -c user.name="Harbor Oracle" -c user.email="oracle@harbor.dev" \
        commit -m "Apply oracle fix patch" --no-verify || true
    echo "Changes committed to git."
else
    echo "Missing /solution/fix.patch"
    exit 1
fi
