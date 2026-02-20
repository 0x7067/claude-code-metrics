# Napkin - Working Notes

## Grafana Dashboard Learnings

### calculateField transformation
- Only supports **binary operations** (two operands at a time)
- For expressions like `A / (B + C)`, chain two steps:
  1. `B + C = D` (intermediate result)
  2. `A / D` (final result)

### Dashboard links
- `type: "dashboards"` does **tag-based search** and ignores the `url` field
- Use `type: "link"` for direct URL navigation

### Template variables
- Set `"refresh": 2` (on time range change) so variables pick up new label values

## OpenTelemetry / Prometheus

### Metric naming conventions (OTel -> Prometheus)
- Dots become underscores (`session.duration` -> `session_duration`)
- Unit suffix is appended automatically (`_seconds`, `_bytes`, etc.)
- Counters get `_total` suffix

## Repo-Specific Notes

- Dashboard JSON files are large (3800+ lines). Use offset/limit when reading.
- Heredocs in bash don't work in sandboxed mode (can't create temp files). Use inline strings instead.
- Running long `python3 -c` one-liners can fail with `unmatched "` errors; for multi-line scripts, use an escalated heredoc.

## Grafana Variable Gotcha

- Claude Code ≥2.1.45 no longer emits a `project` resource attribute in OTLP telemetry
- Without `project` labels on active series, `label_values(metric, project)` returns nothing
- Grafana's "All" for a variable with no values generates a non-`.*` regex → sessions without `project` label get filtered OUT
- Fix: add `"allValue": ".*"` to the variable definition in the dashboard JSON → "All" always expands to `.*` regardless of available values
- All 40+ sessions in the last 24h had NO project label; historical (>24h old stale) sessions do
