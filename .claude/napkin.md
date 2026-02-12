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
