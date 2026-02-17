#!/usr/bin/env bash
set -euo pipefail

OUTPUT_PATH="${1:-web_panel_repo.zip}"

git archive --format=zip --output "$OUTPUT_PATH" HEAD

echo "ZIP archive created: $OUTPUT_PATH"
