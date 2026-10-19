#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 || $# -gt 2 ]]; then
    echo "Usage: $0 run_directory [output_filename]" >&2
    exit 1
fi

SOURCE_DIR="$1"
OUTPUT_FILENAME="${2:-submission.zip}"

if [[ "$OUTPUT_FILENAME" = /* ]]; then
    OUTPUT="$OUTPUT_FILENAME"
else
    OUTPUT="$PWD/$OUTPUT_FILENAME"
fi

if [[ ! -d "$SOURCE_DIR" ]]; then
    echo "Error: directory does not exist: $SOURCE_DIR" >&2
    exit 1
fi

if [[ -e "$OUTPUT" ]]; then
    echo "Error: file already exists: $OUTPUT" >&2
    exit 1
fi

(
    cd "$SOURCE_DIR"
    zip -r -9 -q "$OUTPUT" .
)

echo "Archive created: $OUTPUT"
