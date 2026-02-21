#!/bin/bash
set -euo pipefail

PROJECTS_DIR="/claude-projects"
OUTPUT_DIR="/transcripts"
BACKUP_DIR="/sessions-backup"
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

has_messages() {
  local session_file="$1"
  python3 - "$session_file" <<'PY'
import json, sys
with open(sys.argv[1]) as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        msg = data.get("message", {})
        if isinstance(msg, dict) and msg.get("role") in ("user", "assistant"):
            sys.exit(0)
sys.exit(1)
PY
}

cleanup_empty() {
  python3 - "$OUTPUT_DIR" <<'PY'
import os, sys, shutil
from html.parser import HTMLParser

class MsgCounter(HTMLParser):
    def __init__(self):
        super().__init__()
        self.count = 0
    def handle_starttag(self, tag, attrs):
        for _, val in attrs:
            if val and "message" in val.split():
                self.count += 1

output_dir = sys.argv[1]
removed = 0
for entry in os.listdir(output_dir):
    if entry == "all":
        continue
    d = os.path.join(output_dir, entry)
    idx = os.path.join(d, "index.html")
    if not os.path.isfile(idx):
        continue
    # Check subagents first
    sa_dir = os.path.join(d, "subagents")
    if os.path.isdir(sa_dir):
        for sa in os.listdir(sa_dir):
            sa_page = os.path.join(sa_dir, sa, "page-001.html")
            if not os.path.isfile(sa_page):
                continue
            p = MsgCounter()
            with open(sa_page) as f:
                p.feed(f.read())
            if p.count == 0:
                shutil.rmtree(os.path.join(sa_dir, sa))
                removed += 1
    # Check main transcript
    page = os.path.join(d, "page-001.html")
    if not os.path.isfile(page):
        continue
    p = MsgCounter()
    with open(page) as f:
        p.feed(f.read())
    if p.count == 0:
        shutil.rmtree(d)
        removed += 1

if removed:
    print(f"  Cleaned up {removed} empty transcript(s)")
PY
}

generate() {
  # Back up JSONL session files to persistent volume
  if [ -d "$PROJECTS_DIR" ] && [ "$(ls -A "$PROJECTS_DIR" 2>/dev/null)" ]; then
    rsync -a "$PROJECTS_DIR/" "$BACKUP_DIR/"
  fi

  cleanup_empty

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

    if ! has_messages "$session_file"; then
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
    _cct_output=$(claude-code-transcripts json "$session_file" -o "$session_dir" 2>&1)
    _cct_exit=$?
    echo "$_cct_output" | grep -v "Could not auto-detect GitHub repo" || true
    if [ "$_cct_exit" -ne 0 ]; then
      echo "  ERROR: failed to generate transcript for $session_file" >&2
      failed=$((failed + 1))
      continue
    fi
    processed=$((processed + 1))
  done < <(find "$PROJECTS_DIR" "$BACKUP_DIR" -name "*.jsonl" -type f)

  # Generate the combined index using 'all' command
  _all_output=$(claude-code-transcripts all -s "$PROJECTS_DIR" -o "$OUTPUT_DIR/all" -q 2>&1)
  _all_exit=$?
  echo "$_all_output" | grep -v "Could not auto-detect GitHub repo" || true
  if [ "$_all_exit" -ne 0 ]; then
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
