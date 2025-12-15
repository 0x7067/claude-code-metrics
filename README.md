# Claude Code Metrics

Observability stack for collecting and visualizing Claude Code telemetry.

## Prerequisites

- Docker and Docker Compose

## Setup

1. Copy and configure environment variables:
   ```bash
   cp .env.example .env
   ```

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

4. Access Grafana at http://localhost:3000 (credentials from .env)

## Services

| Service | Port | Description |
|---------|------|-------------|
| Grafana | 3000 | Dashboards |
| Prometheus | 9090 | Metrics storage |
| OTEL Collector | 4317 | OTLP gRPC endpoint |
| OTEL Collector | 4318 | OTLP HTTP endpoint |

## Stop

```bash
docker compose down
```
