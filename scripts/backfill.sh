#!/bin/bash
set -euo pipefail

# Backfill Prometheus metrics from Claude Code JSONL session files.
# Usage: ./scripts/backfill.sh [--dry-run]

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
OM_FILE="/tmp/claude/backfill.om"

DRY_RUN=""
if [[ "${1:-}" == "--dry-run" ]]; then
  DRY_RUN="--dry-run"
fi

echo "==> Step 1: Generate OpenMetrics file"
mkdir -p "$(dirname "$OM_FILE")"
uv run "$SCRIPT_DIR/backfill-metrics.py" --output "$OM_FILE" $DRY_RUN

if [[ -n "$DRY_RUN" ]]; then
  echo "Dry run complete."
  exit 0
fi

echo "==> Step 2: Import into Prometheus TSDB"
docker cp "$OM_FILE" prometheus:/tmp/backfill.om
docker exec prometheus promtool tsdb create-blocks-from openmetrics /tmp/backfill.om /prometheus

echo "==> Step 3: Reload Prometheus"
curl -sf -X POST http://localhost:9090/-/reload
echo " OK"

echo "==> Step 4: Cleanup"
docker exec prometheus rm -f /tmp/backfill.om || true
rm -f "$OM_FILE"

echo "==> Done. Check Grafana at http://localhost:3500"
