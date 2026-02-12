# Metrics Mapping and Dashboard Expectations

## Metric Name Mapping

| Claude Code Metric (OTel) | Prometheus Metric (Grafana) | Unit | Notes |
| --- | --- | --- | --- |
| `claude_code.session.count` | `claude_code_session_count_total` | count | Session counter (one per session). |
| `claude_code.lines_of_code.count` | `claude_code_lines_of_code_count_total` | count | `type` label: `added`, `removed`. |
| `claude_code.pull_request.count` | `claude_code_pull_request_count_total` | count | Session-level. |
| `claude_code.commit.count` | `claude_code_commit_count_total` | count | Session-level. |
| `claude_code.cost.usage` | `claude_code_cost_usage_USD_total` | USD | Model-scoped cost. |
| `claude_code.token.usage` | `claude_code_token_usage_tokens_total` | tokens | `type` and `model` labels. |
| `claude_code.code_edit_tool.decision` | `claude_code_code_edit_tool_decision_total` | count | `tool`, `decision`, `language` labels. |
| `claude_code.active_time.total` | `claude_code_active_time_seconds_total` | s | Session-level. |

## Attributes and Labels

Standard attributes are exported as Prometheus labels. The dashboards expect:
- `session.id` -> `session_id` (requires `OTEL_METRICS_INCLUDE_SESSION_ID=true`)
- `organization.id` -> `organization_id`
- `user.account_uuid` -> `user_account_uuid` (requires `OTEL_METRICS_INCLUDE_ACCOUNT_UUID=true`)
- `app.version` -> `app_version` (requires `OTEL_METRICS_INCLUDE_VERSION=true`)
- `terminal.type` -> `terminal_type`

Additional metric labels:
- `model` for cost and token metrics
- `type` for token usage and lines of code
- `decision`, `tool`, `language` for code edit tool decisions

## Label Baseline and Exceptions

Baseline labels (when enabled) are expected on all metrics:
- `session_id`
- `organization_id`
- `user_account_uuid`
- `terminal_type`
- `app_version` (optional)

Exceptions and additions:
- `model` is **only** present on cost and token metrics.
- `type` is only present on token usage and lines of code metrics.
- `decision`, `tool`, `language` are only present on tool decision metrics.

Dashboard segmentation rule:
- The `Model` filter should only affect cost and token panels. Session-level metrics should not be filtered by `model`.

## Project Label (Optional)

The dashboards filter by `project`, but `project` is not a standard attribute. If you want the `Project` variable to work:
- Set `OTEL_RESOURCE_ATTRIBUTES=project=your-project`
- Use a value without spaces or special characters

If `project` is not set, remove the project filter from queries or set a default.

## Cardinality Controls

These environment variables affect dashboard functionality:
- `OTEL_METRICS_INCLUDE_SESSION_ID` must be `true` for session-level tables and links.
- `OTEL_METRICS_INCLUDE_ACCOUNT_UUID` should stay `true` if you want per-user analysis.
- `OTEL_METRICS_INCLUDE_VERSION` is optional, used only for version breakdowns.

## Query Patterns Used in Dashboards

Use a consistent pattern to avoid misreading counters:
- Cumulative totals: `max_over_time(<counter>[$__range])`
- Period totals: `increase(<counter>[$__range])`
- Rates: `rate(<counter>[$__rate_interval])`

## How to Read These Panels

### Cost and Tokens

- **Cost Over Time**: cost accrued per interval in the selected range.  
  Example:
  ```
  sum(increase(claude_code_cost_usage_USD_total{project=~"$project",model=~"$model"}[$__rate_interval]))
  ```
- **Daily Cost**: daily cost using a fixed 1d bucket.  
  Example:
  ```
  sum(increase(claude_code_cost_usage_USD_total{project=~"$project",model=~"$model"}[1d]))
  ```
- **Spending Rate ($/hour)**: rolling hourly spend rate.  
  Example:
  ```
  sum(rate(claude_code_cost_usage_USD_total{project=~"$project",model=~"$model"}[$__rate_interval])) * 3600
  ```
- **Token Usage by Type**: tokens consumed per interval by `type`.  
  Example:
  ```
  sum(increase(claude_code_token_usage_tokens_total{type="input",project=~"$project",model=~"$model"}[$__rate_interval]))
  ```
- **Token Usage by Model**: tokens per interval grouped by `model`.  
  Example:
  ```
  sum by (model) (increase(claude_code_token_usage_tokens_total{project=~"$project",model=~"$model"}[$__rate_interval]))
  ```

### Sessions and Activity

- **Sessions / Period Sessions**: count of sessions with a session counter signal in range.  
  Example:
  ```
  count(sum by (session_id) (max_over_time(claude_code_session_count_total{project=~"$project"}[$__range])) > 0)
  ```
- **Active Time**: cumulative active time across sessions.  
  Example:
  ```
  sum(max_over_time(claude_code_active_time_seconds_total{project=~"$project"}[$__range]))
  ```
- **Lines of Code (Added/Removed)**: lines changed per interval.  
  Example:
  ```
  sum(increase(claude_code_lines_of_code_count_total{type="added",project=~"$project"}[$__rate_interval]))
  ```

### Tool Usage

- **Tool Decisions**: total accept/reject decisions in range.  
  Example:
  ```
  sum(increase(claude_code_code_edit_tool_decision_total{decision="accept",project=~"$project"}[$__range]))
  ```
- **Tool Decisions by Tool**: decisions grouped by tool name.  
  Example:
  ```
  sum by (tool) (increase(claude_code_code_edit_tool_decision_total{project=~"$project"}[$__range]))
  ```
- **Tool Decisions by Language**: decisions grouped by file language.  
  Example:
  ```
  sum by (language) (increase(claude_code_code_edit_tool_decision_total{project=~"$project"}[$__range]))
  ```
- **Tool Call Frequency (Loki)**: tool usage from transcripts using `hook_name` from promtail (`PreToolUse:<Tool>`).  
  Example:
  ```
  sum by (tool_name) (label_replace(count_over_time({job="claude-transcripts",hook_name=~"PreToolUse:.+"}[$__auto]), "tool_name", "$1", "hook_name", "PreToolUse:(.+)"))
  ```
  Note: Loki labels are set at ingestion time. After changing promtail labels/pipeline, only newly ingested logs reflect the new labels.

### Logs and Events (This Repo)

- The Claude Code spec defines OTEL log events (`claude_code.user_prompt`, `claude_code.tool_result`, etc.).
- This repo does **not** ingest OTEL logs into Loki. Instead, it scrapes transcript JSONL files via promtail.
- As a result, event fields in the spec are **not** available in Loki unless you add an OTEL logs → Loki pipeline.

### Screenshots

Add screenshots for quick visual reference:
- `docs/screenshots/overview-cost-tokens.png`
- `docs/screenshots/sessions-table.png`
- `docs/screenshots/tool-decisions.png`
- `docs/screenshots/tool-usage-frequency.png`

## Temporality Alignment

The OTEL Collector currently converts delta sums to cumulative (`deltatocumulative`). This must match Claude Code’s exporter temporality:
- If Claude Code emits delta counters, keep `deltatocumulative`.
- If Claude Code emits cumulative counters, remove it to avoid double counting.
