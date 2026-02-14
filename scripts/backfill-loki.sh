#!/bin/bash
set -euo pipefail

# Backfill Loki from Claude Code JSONL session files.
# Usage: ./scripts/backfill-loki.sh [--dry-run] [--before YYYY-MM-DD] [...]

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "==> Backfilling Loki from JSONL files"
uv run "$SCRIPT_DIR/backfill-loki.py" "$@"
echo "==> Done"
