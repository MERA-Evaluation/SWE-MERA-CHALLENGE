#!/usr/bin/env bash
set -o errexit
set -o nounset
set -o pipefail
set -o posix

readonly DIRNAME="$(dirname "$0")"
if [ "$#" -ne 1 ]
then
    echo "Usage: $0 <run-dir>" >&2
    exit 1
fi

zip -r -9 -q submission.zip "${DIRNAME}/../$1"
