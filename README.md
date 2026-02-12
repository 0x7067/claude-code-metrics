# Claude Code Metrics

Observability stack for collecting and visualizing Claude Code telemetry.

## Prerequisites

- Docker and Docker Compose

## Setup

1. Copy and configure environment variables:
   ```bash
   cp .env.example .env
   ```
   Set `GRAFANA_ADMIN_PASSWORD` in `.env` to a strong password before starting.

2. Start the stack:
   ```bash
   docker compose up -d
   ```

3. Configure Claude Code to send telemetry:
   ```bash
   export CLAUDE_CODE_ENABLE_TELEMETRY=1
   export OTEL_METRICS_EXPORTER=otlp
   export OTEL_LOGS_EXPORTER=otlp
   export OTEL_EXPORTER_OTLP_PROTOCOL=grpc
   export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
   ```

4. Access Grafana at http://localhost:3500 (credentials from .env)

## Metrics and Labels

The dashboards assume the standard Claude Code metric set and labels. See `docs/metrics.md` for the mapping between Claude Code metric names and the Prometheus names used in Grafana.

If you want the `Project` filter to work, define a `project` resource attribute for each environment:

```bash
export OTEL_RESOURCE_ATTRIBUTES="project=my-project"
```

Session-level dashboards require `OTEL_METRICS_INCLUDE_SESSION_ID=true` (default is true).
Model filtering only applies to cost and token panels; session-level metrics are not model-scoped.
This repo uses promtail to scrape transcript logs; OTEL log events from the spec are not ingested into Loki by default.

## Services

| Service | Port | Description |
|---------|------|-------------|
| Grafana | 3500 | Dashboards |
| Prometheus | 9090 | Metrics storage |
| OTEL Collector | 4317 | OTLP gRPC endpoint |
| OTEL Collector | 4318 | OTLP HTTP endpoint |

## Stop

```bash
docker compose down
```
