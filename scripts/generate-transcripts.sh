#!/bin/bash
set -euo pipefail

PROJECTS_DIR="/claude-projects"
OUTPUT_DIR="/transcripts"
INTERVAL="${TRANSCRIPT_INTERVAL:-120}"

mkdir -p "$OUTPUT_DIR"

generate() {
  echo "[$(date -Iseconds)] Generating transcripts..."

  # Find all JSONL session files and generate individual transcripts
  find "$PROJECTS_DIR" -name "*.jsonl" -type f | while read -r session_file; do
    # Extract session ID from first line of JSONL
    session_id=$(head -1 "$session_file" 2>/dev/null | python3 -c "
import sys, json
try:
    data = json.loads(sys.stdin.readline())
    print(data.get('sessionId', ''))
except:
    pass
" 2>/dev/null || true)

    if [ -z "$session_id" ]; then
      continue
    fi

    session_dir="$OUTPUT_DIR/$session_id"

    # Skip if already generated and source hasn't changed
    if [ -f "$session_dir/index.html" ] && [ "$session_dir/index.html" -nt "$session_file" ]; then
      continue
    fi

    mkdir -p "$session_dir"
    echo "  Processing session: $session_id"
    claude-code-transcripts json "$session_file" -o "$session_dir" 2>/dev/null || true
  done

  # Generate the combined index using 'all' command
  claude-code-transcripts all -s "$PROJECTS_DIR" -o "$OUTPUT_DIR/all" -q 2>/dev/null || true

  echo "[$(date -Iseconds)] Done."
}

# Initial generation
generate

# Loop: regenerate periodically
while true; do
  sleep "$INTERVAL"
  generate
done
