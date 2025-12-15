# Claude Code Metrics

Observability stack for collecting and visualizing Claude Code telemetry.

## Prerequisites

- Docker and Docker Compose

## Setup

1. Start the stack:
   ```bash
   docker compose up -d
   ```

2. Configure Claude Code to send telemetry:
   ```bash
   claude config set --global telemetryBackend otel
   ```

3. Access Grafana at http://localhost:3000 (admin/admin)

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
