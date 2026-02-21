#!/usr/bin/env python3
"""Backfill Loki from Claude Code JSONL session files.

Scans ~/.claude/projects/**/*.jsonl, extracts tool_use/tool_result events,
and pushes structured logs to Loki's native push API.
"""

import argparse
import json
import os
import sys
import time
import urllib.request
import urllib.error
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


def find_jsonl_files(projects_dir):
    """Recursively find all .jsonl files under projects_dir."""
    root = Path(projects_dir)
    if not root.is_dir():
        print(f"ERROR: {projects_dir} is not a directory", file=sys.stderr)
        sys.exit(1)
    return sorted(root.rglob("*.jsonl"))


def parse_timestamp(ts_str):
    """Parse ISO 8601 timestamp to epoch seconds (float)."""
    if not ts_str:
        return None
    ts_str = ts_str.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(ts_str)
        return dt.timestamp()
    except (ValueError, TypeError):
        return None


def extract_project_name(filepath):
    """Extract project name from the JSONL path.

    Path format: ~/.claude/projects/<project-slug>/[subagents/]<session>.jsonl
    """
    parts = Path(filepath).parts
    try:
        idx = parts.index("projects")
        return parts[idx + 1]
    except (ValueError, IndexError):
        return "unknown"


def extract_session_id(filepath):
    """Extract session ID from the JSONL filename (stem without .jsonl)."""
    return Path(filepath).stem


def build_tool_parameters(tool_name, input_dict):
    """Build tool_parameters JSON string for structured metadata."""
    if not isinstance(input_dict, dict):
        return None
    if tool_name == "Bash":
        cmd = input_dict.get("command")
        if isinstance(cmd, str):
            return json.dumps({"bash_command": cmd})
    elif tool_name == "Skill":
        skill = input_dict.get("skill")
        if isinstance(skill, str):
            return json.dumps({"skill_name": skill})
    return None


def extract_tool_events(filepath):
    """Parse a JSONL file and extract tool events.

    Correlates tool_use blocks (assistant messages) with tool_result blocks
    (user messages) by tool_use_id. Returns list of event dicts.
    """
    project = extract_project_name(filepath)
    session_id = extract_session_id(filepath)
    # pending_tools: id -> {name, input, timestamp}
    pending_tools = {}
    events = []

    try:
        with open(filepath, "r", encoding="utf-8") as fh:
            for raw_line in fh:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue

                ts = parse_timestamp(data.get("timestamp"))
                if not ts:
                    continue

                msg = data.get("message")
                if not isinstance(msg, dict):
                    continue

                content = msg.get("content", [])
                if not isinstance(content, list):
                    continue

                # Scan assistant messages for tool_use blocks
                if data.get("type") == "assistant":
                    for block in content:
                        if not isinstance(block, dict):
                            continue
                        if block.get("type") == "tool_use":
                            tool_id = block.get("id")
                            if tool_id:
                                pending_tools[tool_id] = {
                                    "name": block.get("name", "unknown"),
                                    "input": block.get("input", {}),
                                    "timestamp": ts,
                                }

                # Scan user messages for tool_result blocks
                if data.get("type") == "user":
                    for block in content:
                        if not isinstance(block, dict):
                            continue
                        if block.get("type") != "tool_result":
                            continue

                        tool_use_id = block.get("tool_use_id")
                        if not tool_use_id or tool_use_id not in pending_tools:
                            continue

                        pending = pending_tools.pop(tool_use_id)
                        is_error = block.get("is_error", False)
                        success = not is_error

                        # Duration: result timestamp - use timestamp
                        duration_ms = int((ts - pending["timestamp"]) * 1000)
                        # Guard: 0 < d < 600,000ms (10 min)
                        if duration_ms <= 0 or duration_ms > 600_000:
                            duration_ms = None

                        tool_params = build_tool_parameters(
                            pending["name"], pending["input"]
                        )

                        events.append({
                            "timestamp_ns": str(int(ts * 1_000_000_000)),
                            "project": project,
                            "session_id": session_id,
                            "tool_name": pending["name"],
                            "success": success,
                            "duration_ms": duration_ms,
                            "tool_parameters": tool_params,
                        })

    except (OSError, UnicodeDecodeError) as e:
        print(f"  WARN: skipping {filepath}: {e}", file=sys.stderr)

    return events


def push_to_loki(events, loki_url, batch_size, dry_run=False):
    """Group events by project, sort by timestamp, push in batches."""
    # Group by project
    by_project = defaultdict(list)
    for ev in events:
        by_project[ev["project"]].append(ev)

    total_pushed = 0
    total_errors = 0

    for project, proj_events in sorted(by_project.items()):
        proj_events.sort(key=lambda e: e["timestamp_ns"])

        # Push in batches
        for i in range(0, len(proj_events), batch_size):
            batch = proj_events[i : i + batch_size]
            values = []
            for ev in batch:
                log_line = (
                    f"tool_result: {ev['tool_name']} "
                    f"success={str(ev['success']).lower()}"
                )
                metadata = {
                    "event_name": "tool_result",
                    "tool_name": ev["tool_name"],
                    "success": str(ev["success"]).lower(),
                    "session_id": ev["session_id"],
                }
                if ev["duration_ms"] is not None:
                    metadata["duration_ms"] = str(ev["duration_ms"])
                if ev["tool_parameters"]:
                    metadata["tool_parameters"] = ev["tool_parameters"]

                values.append([ev["timestamp_ns"], log_line, metadata])

            payload = {
                "streams": [
                    {
                        "stream": {
                            "service_name": "claude-code",
                            "project": project,
                        },
                        "values": values,
                    }
                ]
            }

            if dry_run:
                total_pushed += len(batch)
                continue

            try:
                _post_json(f"{loki_url}/loki/api/v1/push", payload)
                total_pushed += len(batch)
                time.sleep(0.1)  # pace requests to avoid 429
            except Exception as e:
                total_errors += 1
                print(
                    f"  ERROR pushing batch for {project}: {e}",
                    file=sys.stderr,
                )

    return total_pushed, total_errors


def _post_json(url, payload, max_retries=5):
    """POST JSON payload using stdlib urllib, with retry on 429."""
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    for attempt in range(max_retries):
        try:
            with urllib.request.urlopen(req) as resp:
                resp.read()
            return
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            if e.code == 429 and attempt < max_retries - 1:
                wait = 2 ** attempt
                print(
                    f"  429 retry {attempt + 1}/{max_retries} "
                    f"(wait {wait}s): {body[:200]}",
                    file=sys.stderr,
                )
                time.sleep(wait)
                continue
            raise Exception(f"HTTP {e.code}: {body[:300]}")


def _print_summary(events):
    """Print summary stats to stderr."""
    if not events:
        print("No tool events found.", file=sys.stderr)
        return

    projects = set()
    tool_counts = defaultdict(int)
    success_count = 0
    error_count = 0
    durations = []

    for ev in events:
        projects.add(ev["project"])
        tool_counts[ev["tool_name"]] += 1
        if ev["success"]:
            success_count += 1
        else:
            error_count += 1
        if ev["duration_ms"] is not None:
            durations.append(ev["duration_ms"])

    # Timestamp range
    ts_values = [int(ev["timestamp_ns"]) for ev in events]
    date_min = datetime.fromtimestamp(
        min(ts_values) / 1e9, tz=timezone.utc
    ).strftime("%Y-%m-%d")
    date_max = datetime.fromtimestamp(
        max(ts_values) / 1e9, tz=timezone.utc
    ).strftime("%Y-%m-%d")

    avg_dur = sum(durations) / len(durations) if durations else 0

    print(f"\n{'=' * 60}", file=sys.stderr)
    print(f"  Total events:    {len(events):,}", file=sys.stderr)
    print(f"  Projects:        {len(projects)}", file=sys.stderr)
    print(f"  Date range:      {date_min} to {date_max}", file=sys.stderr)
    print(f"  Success:         {success_count:,}", file=sys.stderr)
    print(f"  Errors:          {error_count:,}", file=sys.stderr)
    print(f"  Avg duration:    {avg_dur:,.0f} ms", file=sys.stderr)
    print(f"\n  By tool (top 15):", file=sys.stderr)
    for tool, count in sorted(
        tool_counts.items(), key=lambda x: x[1], reverse=True
    )[:15]:
        print(f"    {tool}: {count:,}", file=sys.stderr)
    print(f"\n  By project:", file=sys.stderr)
    project_counts = defaultdict(int)
    for ev in events:
        project_counts[ev["project"]] += 1
    for proj in sorted(
        project_counts, key=project_counts.get, reverse=True
    )[:10]:
        print(f"    {proj}: {project_counts[proj]:,}", file=sys.stderr)
    print(f"{'=' * 60}\n", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(
        description="Backfill Loki from Claude Code JSONL files."
    )
    parser.add_argument(
        "--projects-dir",
        default=os.path.expanduser("~/.claude/projects"),
        help="Path to Claude projects directory (default: ~/.claude/projects)",
    )
    parser.add_argument(
        "--loki-url",
        default="http://localhost:3100",
        help="Loki base URL (default: http://localhost:3100)",
    )
    parser.add_argument(
        "--before",
        default=None,
        help="Only include events before this date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Number of events per Loki push request (default: 100)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and show summary without pushing to Loki",
    )
    args = parser.parse_args()

    # Parse --before into epoch ns
    before_ns = None
    if args.before:
        try:
            dt = datetime.strptime(args.before, "%Y-%m-%d").replace(
                tzinfo=timezone.utc
            )
            before_ns = str(int(dt.timestamp() * 1_000_000_000))
        except ValueError:
            print(
                f"ERROR: invalid date format '{args.before}', use YYYY-MM-DD",
                file=sys.stderr,
            )
            sys.exit(1)

    jsonl_files = find_jsonl_files(args.projects_dir)
    print(f"Found {len(jsonl_files)} JSONL files", file=sys.stderr)

    all_events = []
    for i, fp in enumerate(jsonl_files, 1):
        if i % 100 == 0:
            print(f"  Parsing {i}/{len(jsonl_files)}...", file=sys.stderr)
        events = extract_tool_events(fp)
        all_events.extend(events)

    print(f"Extracted {len(all_events):,} tool events", file=sys.stderr)

    # Apply --before filter
    if before_ns:
        all_events = [ev for ev in all_events if ev["timestamp_ns"] < before_ns]
        print(
            f"After --before filter: {len(all_events):,} events",
            file=sys.stderr,
        )

    _print_summary(all_events)

    if not all_events:
        sys.exit(0)

    if args.dry_run:
        print("Dry run — no data pushed to Loki.", file=sys.stderr)
        sys.exit(0)

    print(
        f"Pushing to Loki at {args.loki_url} (batch size: {args.batch_size})",
        file=sys.stderr,
    )
    pushed, errors = push_to_loki(
        all_events, args.loki_url, args.batch_size, dry_run=False
    )
    print(f"Pushed {pushed:,} events ({errors} errors)", file=sys.stderr)


if __name__ == "__main__":
    main()
