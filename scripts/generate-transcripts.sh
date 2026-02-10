#!/bin/bash
set -euo pipefail

PROJECTS_DIR="/claude-projects"
OUTPUT_DIR="/transcripts"
INTERVAL="${TRANSCRIPT_INTERVAL:-120}"

mkdir -p "$OUTPUT_DIR"

extract_session_id() {
  local session_file="$1"

  python3 - "$session_file" <<'PY'
import json
import sys

session_file = sys.argv[1]

try:
    with open(session_file, "r", encoding="utf-8") as fh:
        for raw_line in fh:
            line = raw_line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            session_id = data.get("sessionId")
            if session_id:
                print(session_id)
                break
except Exception:
    pass
PY
}

generate() {
  echo "[$(date -Iseconds)] Generating transcripts..."
  local processed=0
  local skipped=0
  local failed=0

  # Find all JSONL session files and generate individual transcripts
  while IFS= read -r session_file; do
    session_id="$(extract_session_id "$session_file")"

    if [ -z "$session_id" ]; then
      echo "  Skipping (sessionId not found): $session_file" >&2
      skipped=$((skipped + 1))
      continue
    fi

    if [[ "$session_file" == *"/subagents/"* ]]; then
      agent_id="$(basename "$session_file" .jsonl)"
      session_dir="$OUTPUT_DIR/$session_id/subagents/$agent_id"
    else
      session_dir="$OUTPUT_DIR/$session_id"
    fi

    # Skip if already generated and source hasn't changed
    if [ -f "$session_dir/index.html" ] && [ "$session_dir/index.html" -nt "$session_file" ]; then
      skipped=$((skipped + 1))
      continue
    fi

    mkdir -p "$session_dir"
    echo "  Processing session: $session_id"
    if ! claude-code-transcripts json "$session_file" -o "$session_dir"; then
      echo "  ERROR: failed to generate transcript for $session_file" >&2
      failed=$((failed + 1))
      continue
    fi
    processed=$((processed + 1))
  done < <(find "$PROJECTS_DIR" -name "*.jsonl" -type f)

  # Generate the combined index using 'all' command
  if ! claude-code-transcripts all -s "$PROJECTS_DIR" -o "$OUTPUT_DIR/all" -q; then
    echo "  ERROR: failed to generate combined transcript index" >&2
    failed=$((failed + 1))
  fi

  echo "[$(date -Iseconds)] Done. processed=$processed skipped=$skipped failed=$failed"
}

# Initial generation
generate

# Loop: regenerate periodically
while true; do
  sleep "$INTERVAL"
  generate
done
