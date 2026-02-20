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

### Tool Details

The "Most Used Commands" panel extracts program names from Bash tool events and is always available. The "Most Used Skills" panel requires an additional environment variable to capture skill names:

```bash
export OTEL_LOG_TOOL_DETAILS=1
```

## Services

| Service | Port | Description |
|---------|------|-------------|
| Grafana | 3500 | Dashboards |
| Prometheus | 9090 | Metrics storage |
| OTEL Collector | 4317 | OTLP gRPC endpoint |
| OTEL Collector | 4318 | OTLP HTTP endpoint |

## Grafana Cloud (optional dual-write)

The stack can export telemetry to Grafana Cloud **in addition to** the local stack. When the env vars below are unset, the exporters are registered but effectively disabled (empty endpoint).

### Credentials

1. In [Grafana Cloud Portal](https://grafana.com/auth/sign-in), open your stack.
2. Go to **Security → Access Policies** and create a new access policy with these scopes:
   - `metrics:write` — push OTEL metrics
   - `logs:write` — push OTEL logs and Loki transcript logs
   - `traces:write` — (optional, for future trace support)
3. Generate a token for the policy — this is your `GRAFANA_CLOUD_API_TOKEN`.
4. Find your instance ID and OTLP endpoint under **Connections → OpenTelemetry**.
5. Find your Loki push URL under **Connections → Data sources → Loki** (the "URL" field).

### Required env vars

Add these to your `.env` file (copy from the example below):

```bash
# OTEL metrics + logs (via OTEL Collector)
GRAFANA_CLOUD_OTLP_ENDPOINT=https://otlp-gateway-<region>.grafana.net/otlp
GRAFANA_CLOUD_INSTANCE_ID=<numeric-instance-id>
GRAFANA_CLOUD_API_TOKEN=<your-api-token>

# Loki transcript logs (via Promtail) — instance ID and token are reused
GRAFANA_CLOUD_LOKI_ENDPOINT=https://logs-prod-<region>.grafana.net/loki/api/v1/push
```

Restart the stack after adding credentials:

```bash
docker compose up -d --force-recreate otel-collector promtail
```

### Dashboards

Import the dashboard JSON from `grafana/dashboards/claude-code.json` into your Grafana Cloud instance via **Dashboards → Import**.

> **Note:** Recording rules defined in `recording-rules.yml` must be recreated manually in Grafana Cloud under **Alerting → Alert rules** (Mimir recording rules). Panels that rely on recording rules will show no data until they are created.

## Stop

```bash
docker compose down
```
