#!/usr/bin/env python3
"""Backfill Prometheus metrics from Claude Code JSONL session files.

Scans ~/.claude/projects/**/*.jsonl, extracts token usage from assistant events,
and outputs OpenMetrics format suitable for `promtool tsdb create-blocks-from openmetrics`.
"""

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

# Pricing per 1M tokens (USD)
MODEL_PRICING = {
    "claude-opus-4": {
        "input": 15.0,
        "output": 75.0,
        "cacheCreation": 18.75,
        "cacheRead": 1.50,
    },
    "claude-sonnet-4": {
        "input": 3.0,
        "output": 15.0,
        "cacheCreation": 3.75,
        "cacheRead": 0.30,
    },
    "claude-haiku-4": {
        "input": 0.80,
        "output": 4.0,
        "cacheCreation": 1.0,
        "cacheRead": 0.08,
    },
}


def match_pricing(model_id):
    """Match a model ID like 'claude-sonnet-4-5-20250929' to its pricing tier."""
    if not model_id:
        return MODEL_PRICING["claude-sonnet-4"]  # fallback
    m = model_id.lower()
    if "opus" in m:
        return MODEL_PRICING["claude-opus-4"]
    if "haiku" in m:
        return MODEL_PRICING["claude-haiku-4"]
    return MODEL_PRICING["claude-sonnet-4"]


def parse_timestamp(ts_str):
    """Parse ISO 8601 timestamp to epoch seconds."""
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


_GIT_COMMIT_RE = re.compile(r"\bgit\s+commit\b")
_GH_PR_CREATE_RE = re.compile(r"\bgh\s+pr\s+create\b")


def parse_file(filepath):
    """Parse a single JSONL file. Returns raw parsed data dict or None."""
    session_id = None
    project = extract_project_name(filepath)
    tokens = defaultdict(lambda: defaultdict(int))
    timestamps = []
    lines_added = 0
    lines_removed = 0
    # Track pending Bash tool_use IDs awaiting result confirmation
    pending_commits = set()   # tool_use IDs for git commit commands
    pending_prs = set()       # tool_use IDs for gh pr create commands
    commits = 0
    pull_requests = 0

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

                if not session_id:
                    sid = data.get("sessionId")
                    if sid:
                        session_id = sid

                ts = parse_timestamp(data.get("timestamp"))
                if ts:
                    timestamps.append(ts)

                msg = data.get("message")
                if not isinstance(msg, dict):
                    continue

                content = msg.get("content", [])
                if not isinstance(content, list):
                    continue

                # Check tool_result blocks (in "user" events) for commit/PR success
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    if block.get("type") == "tool_result":
                        tuid = block.get("tool_use_id")
                        if tuid and not block.get("is_error"):
                            if tuid in pending_commits:
                                commits += 1
                                pending_commits.discard(tuid)
                            elif tuid in pending_prs:
                                pull_requests += 1
                                pending_prs.discard(tuid)
                        else:
                            pending_commits.discard(tuid)
                            pending_prs.discard(tuid)

                if data.get("type") != "assistant":
                    continue

                # Extract tool_use blocks for LOC, commits, PRs
                for block in content:
                    if not isinstance(block, dict) or block.get("type") != "tool_use":
                        continue
                    name = block.get("name", "")
                    inp = block.get("input", {})
                    if not isinstance(inp, dict):
                        continue

                    if name == "Edit":
                        old = inp.get("old_string", "")
                        new = inp.get("new_string", "")
                        if isinstance(old, str) and old:
                            lines_removed += old.count("\n") + 1
                        if isinstance(new, str) and new:
                            lines_added += new.count("\n") + 1
                    elif name == "Write":
                        wc = inp.get("content", "")
                        if isinstance(wc, str) and wc:
                            lines_added += wc.count("\n") + 1
                    elif name == "Bash":
                        cmd = inp.get("command", "")
                        if isinstance(cmd, str):
                            if _GIT_COMMIT_RE.search(cmd):
                                pending_commits.add(block.get("id"))
                            elif _GH_PR_CREATE_RE.search(cmd):
                                pending_prs.add(block.get("id"))

                # Token accounting (only on assistant events with usage)
                usage = msg.get("usage")
                if not usage:
                    continue

                model = msg.get("model", "unknown")
                tokens[model]["input"] += usage.get("input_tokens", 0)
                tokens[model]["output"] += usage.get("output_tokens", 0)
                tokens[model]["cacheRead"] += usage.get("cache_read_input_tokens", 0)
                tokens[model]["cacheCreation"] += usage.get(
                    "cache_creation_input_tokens", 0
                )
    except (OSError, UnicodeDecodeError) as e:
        print(f"  WARN: skipping {filepath}: {e}", file=sys.stderr)
        return None

    if not session_id or not tokens:
        return None

    return {
        "session_id": session_id,
        "project": project,
        "tokens": dict(tokens),
        "timestamps": timestamps,
        "lines_added": lines_added,
        "lines_removed": lines_removed,
        "commits": commits,
        "pull_requests": pull_requests,
    }


def merge_into_sessions(parsed_files):
    """Merge parsed file data by session_id (subagents fold into parent)."""
    sessions = {}
    for pf in parsed_files:
        sid = pf["session_id"]
        if sid not in sessions:
            sessions[sid] = {
                "session_id": sid,
                "project": pf["project"],
                "tokens": defaultdict(lambda: defaultdict(int)),
                "timestamps": [],
                "lines_added": 0,
                "lines_removed": 0,
                "commits": 0,
                "pull_requests": 0,
            }
        s = sessions[sid]
        s["timestamps"].extend(pf["timestamps"])
        for model, counts in pf["tokens"].items():
            for token_type, count in counts.items():
                s["tokens"][model][token_type] += count
        s["lines_added"] += pf["lines_added"]
        s["lines_removed"] += pf["lines_removed"]
        s["commits"] += pf["commits"]
        s["pull_requests"] += pf["pull_requests"]

    # Finalize: compute cost and time ranges
    result = []
    for s in sessions.values():
        tokens = {m: dict(c) for m, c in s["tokens"].items()}

        cost_by_model = {}
        for model, counts in tokens.items():
            pricing = match_pricing(model)
            cost = sum(
                counts.get(t, 0) * pricing.get(t, 0) / 1_000_000
                for t in counts
            )
            cost_by_model[model] = cost

        ts_list = s["timestamps"]
        start_ts = min(ts_list) if ts_list else None
        end_ts = max(ts_list) if ts_list else None
        active_seconds = (end_ts - start_ts) if start_ts and end_ts else 0.0

        result.append({
            "session_id": s["session_id"],
            "project": s["project"],
            "tokens": tokens,
            "cost_by_model": cost_by_model,
            "active_seconds": active_seconds,
            "start_ts": start_ts,
            "end_ts": end_ts,
            "lines_added": s["lines_added"],
            "lines_removed": s["lines_removed"],
            "commits": s["commits"],
            "pull_requests": s["pull_requests"],
        })
    return result


def find_jsonl_files(projects_dir):
    """Recursively find all .jsonl files under projects_dir."""
    root = Path(projects_dir)
    if not root.is_dir():
        print(f"ERROR: {projects_dir} is not a directory", file=sys.stderr)
        sys.exit(1)
    return sorted(root.rglob("*.jsonl"))


def format_openmetrics(sessions):
    """Format sessions as OpenMetrics text.

    Emits linearly interpolated data points at ~60s intervals to match
    scrape-like density and avoid Prometheus increase() extrapolation.
    Timestamps are Unix epoch seconds (float) per OpenMetrics spec.
    """
    lines = []
    step = 60  # seconds

    def fmt(v):
        if v == int(v):
            return str(int(v))
        return f"{v:.6f}"

    def emit(metric, labels, value, start, end):
        val = float(value)
        duration = end - start
        n = max(1, int(duration / step)) if duration >= step else 1
        # Pre-compensate for Prometheus increase() extrapolation.
        # For counters starting at 0, Prometheus only extrapolates forward
        # (not backward), giving factor (2N+1)/(2N). Emitting val*2N/(2N+1)
        # cancels this so increase() returns the exact true value.
        for i in range(n + 1):
            frac = 2 * i / (2 * n + 1)
            lines.append(
                f"{metric}{{{labels}}} {fmt(val * frac)} {start + duration * i / n:.3f}"
            )

    # Token usage
    lines.append(
        "# HELP claude_code_token_usage_tokens_total Cumulative token usage by type."
    )
    lines.append("# TYPE claude_code_token_usage_tokens_total counter")
    for s in sessions:
        if not s["start_ts"] or not s["end_ts"]:
            continue
        for model, counts in s["tokens"].items():
            for token_type, count in counts.items():
                if count == 0:
                    continue
                labels = (
                    f'session_id="{s["session_id"]}",'
                    f'model="{model}",'
                    f'project="{s["project"]}",'
                    f'type="{token_type}"'
                )
                emit(
                    "claude_code_token_usage_tokens_total",
                    labels, count, s["start_ts"], s["end_ts"],
                )

    # Cost
    lines.append(
        "# HELP claude_code_cost_usage_USD_total Cumulative cost in USD."
    )
    lines.append("# TYPE claude_code_cost_usage_USD_total counter")
    for s in sessions:
        if not s["start_ts"] or not s["end_ts"]:
            continue
        for model, cost in s["cost_by_model"].items():
            if cost == 0:
                continue
            labels = (
                f'session_id="{s["session_id"]}",'
                f'model="{model}",'
                f'project="{s["project"]}"'
            )
            emit(
                "claude_code_cost_usage_USD_total",
                labels, f"{cost:.6f}", s["start_ts"], s["end_ts"],
            )

    # Session count
    lines.append(
        "# HELP claude_code_session_count_total Session count marker."
    )
    lines.append("# TYPE claude_code_session_count_total counter")
    for s in sessions:
        if not s["start_ts"] or not s["end_ts"]:
            continue
        labels = (
            f'session_id="{s["session_id"]}",'
            f'project="{s["project"]}"'
        )
        emit(
            "claude_code_session_count_total",
            labels, 1, s["start_ts"], s["end_ts"],
        )

    # Active time
    lines.append(
        "# HELP claude_code_active_time_seconds_total Estimated active session time."
    )
    lines.append("# TYPE claude_code_active_time_seconds_total counter")
    for s in sessions:
        if not s["start_ts"] or not s["end_ts"] or s["active_seconds"] <= 0:
            continue
        labels = (
            f'session_id="{s["session_id"]}",'
            f'project="{s["project"]}"'
        )
        emit(
            "claude_code_active_time_seconds_total",
            labels, f"{s['active_seconds']:.1f}", s["start_ts"], s["end_ts"],
        )

    # Lines of code
    lines.append(
        "# HELP claude_code_lines_of_code_count_total Lines of code added or removed."
    )
    lines.append("# TYPE claude_code_lines_of_code_count_total counter")
    for s in sessions:
        if not s["start_ts"] or not s["end_ts"]:
            continue
        for loc_type, key in [("added", "lines_added"), ("removed", "lines_removed")]:
            val = s[key]
            if val == 0:
                continue
            labels = (
                f'session_id="{s["session_id"]}",'
                f'project="{s["project"]}",'
                f'type="{loc_type}"'
            )
            emit(
                "claude_code_lines_of_code_count_total",
                labels, val, s["start_ts"], s["end_ts"],
            )

    # Commit count
    lines.append(
        "# HELP claude_code_commit_count_total Number of git commits."
    )
    lines.append("# TYPE claude_code_commit_count_total counter")
    for s in sessions:
        if not s["start_ts"] or not s["end_ts"] or s["commits"] == 0:
            continue
        labels = (
            f'session_id="{s["session_id"]}",'
            f'project="{s["project"]}"'
        )
        emit(
            "claude_code_commit_count_total",
            labels, s["commits"], s["start_ts"], s["end_ts"],
        )

    # Pull request count
    lines.append(
        "# HELP claude_code_pull_request_count_total Number of pull requests created."
    )
    lines.append("# TYPE claude_code_pull_request_count_total counter")
    for s in sessions:
        if not s["start_ts"] or not s["end_ts"] or s["pull_requests"] == 0:
            continue
        labels = (
            f'session_id="{s["session_id"]}",'
            f'project="{s["project"]}"'
        )
        emit(
            "claude_code_pull_request_count_total",
            labels, s["pull_requests"], s["start_ts"], s["end_ts"],
        )

    lines.append("# EOF")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(
        description="Backfill Prometheus metrics from Claude Code JSONL files."
    )
    parser.add_argument(
        "--projects-dir",
        default=os.path.expanduser("~/.claude/projects"),
        help="Path to Claude projects directory (default: ~/.claude/projects)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output file path (default: stdout)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show summary stats without generating output",
    )
    args = parser.parse_args()

    jsonl_files = find_jsonl_files(args.projects_dir)
    print(f"Found {len(jsonl_files)} JSONL files", file=sys.stderr)

    parsed = []
    for i, fp in enumerate(jsonl_files, 1):
        if i % 100 == 0:
            print(f"  Parsing {i}/{len(jsonl_files)}...", file=sys.stderr)
        result = parse_file(fp)
        if result:
            parsed.append(result)

    print(f"Parsed {len(parsed)} files with usage data", file=sys.stderr)

    if not parsed:
        print("No sessions with usage data found.", file=sys.stderr)
        sys.exit(0)

    sessions = merge_into_sessions(parsed)
    print(f"Merged into {len(sessions)} unique sessions", file=sys.stderr)

    # Summary stats
    total_input = sum(
        c.get("input", 0) for s in sessions for c in s["tokens"].values()
    )
    total_output = sum(
        c.get("output", 0) for s in sessions for c in s["tokens"].values()
    )
    total_cache_read = sum(
        c.get("cacheRead", 0) for s in sessions for c in s["tokens"].values()
    )
    total_cache_create = sum(
        c.get("cacheCreation", 0)
        for s in sessions
        for c in s["tokens"].values()
    )
    total_cost = sum(c for s in sessions for c in s["cost_by_model"].values())
    total_active = sum(s["active_seconds"] for s in sessions)
    total_lines_added = sum(s["lines_added"] for s in sessions)
    total_lines_removed = sum(s["lines_removed"] for s in sessions)
    total_commits = sum(s["commits"] for s in sessions)
    total_prs = sum(s["pull_requests"] for s in sessions)

    all_starts = [s["start_ts"] for s in sessions if s["start_ts"]]
    all_ends = [s["end_ts"] for s in sessions if s["end_ts"]]
    date_min = (
        datetime.fromtimestamp(min(all_starts), tz=timezone.utc).strftime("%Y-%m-%d")
        if all_starts else "?"
    )
    date_max = (
        datetime.fromtimestamp(max(all_ends), tz=timezone.utc).strftime("%Y-%m-%d")
        if all_ends else "?"
    )

    model_tokens = defaultdict(int)
    model_cost = defaultdict(float)
    for s in sessions:
        for model, counts in s["tokens"].items():
            model_tokens[model] += sum(counts.values())
        for model, cost in s["cost_by_model"].items():
            model_cost[model] += cost

    project_sessions = defaultdict(int)
    project_cost = defaultdict(float)
    for s in sessions:
        project_sessions[s["project"]] += 1
        project_cost[s["project"]] += sum(s["cost_by_model"].values())

    print(f"\n{'=' * 60}", file=sys.stderr)
    print(f"  Sessions:        {len(sessions)}", file=sys.stderr)
    print(f"  Date range:      {date_min} to {date_max}", file=sys.stderr)
    print(f"  Input tokens:    {total_input:,.0f}", file=sys.stderr)
    print(f"  Output tokens:   {total_output:,.0f}", file=sys.stderr)
    print(f"  Cache read:      {total_cache_read:,.0f}", file=sys.stderr)
    print(f"  Cache creation:  {total_cache_create:,.0f}", file=sys.stderr)
    print(f"  Total cost:      ${total_cost:,.2f}", file=sys.stderr)
    print(f"  Active time:     {total_active / 3600:,.1f} hours", file=sys.stderr)
    print(f"  Lines added:     {total_lines_added:,}", file=sys.stderr)
    print(f"  Lines removed:   {total_lines_removed:,}", file=sys.stderr)
    print(f"  Commits:         {total_commits:,}", file=sys.stderr)
    print(f"  Pull requests:   {total_prs:,}", file=sys.stderr)
    print(f"\n  By model:", file=sys.stderr)
    for model in sorted(model_tokens, key=lambda m: model_cost[m], reverse=True):
        print(
            f"    {model}: {model_tokens[model]:,.0f} tokens, ${model_cost[model]:,.2f}",
            file=sys.stderr,
        )
    print(f"\n  By project (top 10):", file=sys.stderr)
    for proj in sorted(project_cost, key=project_cost.get, reverse=True)[:10]:
        print(
            f"    {proj}: {project_sessions[proj]} sessions, ${project_cost[proj]:,.2f}",
            file=sys.stderr,
        )
    print(f"{'=' * 60}\n", file=sys.stderr)

    if args.dry_run:
        print("Dry run — no output generated.", file=sys.stderr)
        sys.exit(0)

    output = format_openmetrics(sessions)

    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w") as f:
            f.write(output)
        print(f"Wrote {len(output)} bytes to {args.output}", file=sys.stderr)
    else:
        sys.stdout.write(output)


if __name__ == "__main__":
    main()
