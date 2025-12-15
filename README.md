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
   claude config set --global telemetryBackend otel
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
