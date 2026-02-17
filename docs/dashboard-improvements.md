# Dashboard Improvements

Research and recommendations for improving the usefulness and reliability of the Claude Code Metrics Grafana dashboards.

## Summary

After deep analysis of both Grafana dashboards (35+ panels), all infrastructure configs (Docker Compose, Prometheus, OTEL Collector, Loki, Promtail), and the backfill scripts, this document identifies **14 concrete improvements** across usefulness and reliability. The top findings: (1) the dashboard lacks alerting entirely — there is no way to know if costs spike or the stack itself breaks; (2) Loki retention is disabled, meaning logs accumulate forever; (3) several high-value visualizations are missing (efficiency metrics, session timeline, project comparison); and (4) `session_id` as a Prometheus label creates unbounded cardinality risk.

---

## High Priority

### 1. Add Grafana Alerting for Cost and Usage Spikes

- **What**: Create alert rules for daily cost exceeding a threshold, unusually long sessions, and token spending rate anomalies
- **Why**: There is currently **zero alerting** in the entire stack. A runaway session could burn $50+ before you notice. The infrastructure config has an `alertmanager_url` in Loki but no Alertmanager is deployed
- **How**:
  - Add an Alertmanager service to `docker-compose.yml`
  - Create Prometheus alert rules in a new `alert-rules.yml`:
    - `DailyCostHigh`: `sum(increase(claude_code_cost_usage_USD_total[24h])) > 10`
    - `SessionCostHigh`: `max by (session_id)(max_over_time(claude_code_cost_usage_USD_total[$__range])) > 5`
    - `SpendingRateHigh`: `sum(rate(claude_code_cost_usage_USD_total[5m])) * 3600 > 5` (>$5/hr)
  - Configure notification channel (email, Slack webhook, etc.)
- **Effort**: Medium

### 2. Enable Loki Retention (Prevent Unbounded Disk Growth)

- **What**: Enable log retention and compactor deletion in `loki-config.yaml`
- **Why**: `retention_enabled: false` at line 39 of `loki-config.yaml` means **logs are never deleted**. Combined with the 50 MB/s ingestion rate limit, this will fill disk over time. The OTEL collector also pushes structured log events which compound growth
- **How**:
  - In `loki-config.yaml`, set:
    ```yaml
    compactor:
      retention_enabled: true
      delete_request_store: filesystem
    limits_config:
      retention_period: 720h  # 30 days
    ```
  - Consider longer retention for Prometheus (current 90d is fine) vs shorter for Loki (logs are more voluminous)
- **Effort**: Low

### 3. Add a "Session Timeline" Visualization

- **What**: A timeline/Gantt chart showing session start/end times with cost intensity as color encoding
- **Why**: The current "All Sessions" table shows sessions as flat rows with "Last Active" timestamps, but gives no visual sense of **when** sessions happened, how they overlap, or which time periods were most active. This is the most natural question a user has: "when was I using Claude Code and how much did each block cost?"
- **How**:
  - Add a State Timeline panel in `claude-code.json` using:
    ```promql
    max by (session_id) (claude_code_cost_usage_USD_total{project=~"$project"})
    ```
  - Use value mappings to color-code cost ranges (green < $0.50, yellow < $2, red > $2)
  - Place it in the Sessions section, above the table
- **Effort**: Medium

### 4. Add Stack Health / Meta-Monitoring Dashboard

- **What**: A new dashboard (or row in the existing one) showing the health of Prometheus, Loki, OTEL Collector, and Promtail
- **Why**: The observability stack has **zero monitoring of itself**. If Prometheus runs out of disk, Loki stops ingesting, or the OTEL Collector drops metrics, there's no way to know. All services expose self-monitoring metrics that are currently unused
- **How**:
  - Add Prometheus self-scrape target in `prometheus.yml` (`localhost:9090`)
  - Create a "Stack Health" row with panels:
    - `prometheus_tsdb_head_series` — active series count (cardinality monitor)
    - `prometheus_tsdb_size_bytes` — storage size
    - `rate(prometheus_tsdb_compaction_duration_seconds_sum[5m])` — compaction health
    - OTEL Collector: `otelcol_receiver_accepted_metric_points_total` — ingestion rate
    - OTEL Collector: `otelcol_exporter_send_failed_metric_points_total` — export errors
  - Add alerting rules for cardinality > threshold and disk usage > 80%
- **Effort**: Medium

### 5. Add Docker Health Checks to All Services

- **What**: Add `healthcheck` blocks to every service in `docker-compose.yml`
- **Why**: Currently no service has health checks. A container can restart with a broken service inside and Docker considers it "healthy." The `depends_on` directives only check container existence, not service readiness — Grafana may start before Prometheus is ready to serve queries
- **How**: Add to `docker-compose.yml`:
  ```yaml
  prometheus:
    healthcheck:
      test: ["CMD", "wget", "-q", "--spider", "http://localhost:9090/-/healthy"]
      interval: 30s
      timeout: 5s
      retries: 3
  loki:
    healthcheck:
      test: ["CMD", "wget", "-q", "--spider", "http://localhost:3100/ready"]
      interval: 30s
      timeout: 5s
      retries: 3
  grafana:
    healthcheck:
      test: ["CMD", "wget", "-q", "--spider", "http://localhost:3000/api/health"]
      interval: 30s
      timeout: 5s
      retries: 3
  ```
  Then use `depends_on: { prometheus: { condition: service_healthy } }` for ordering
- **Effort**: Low

---

## Medium Priority

### 6. Add "Cost Efficiency" Panel — Cost per Line of Code

- **What**: A stat panel showing `Total Cost / Lines Changed` and a time series of this ratio
- **Why**: Raw cost numbers are less actionable than efficiency metrics. "$5 for 500 lines changed" ($0.01/line) is very different from "$5 for 10 lines changed" ($0.50/line). This directly answers "am I getting value from Claude Code?" — the core question for any user tracking costs
- **How**:
  - Stat panel query:
    ```promql
    sum(max_over_time(claude_code_cost_usage_USD_total{project=~"$project"}[$__range]))
    / clamp_min(
      sum(max_over_time(claude_code_lines_of_code_count_total{project=~"$project"}[$__range])),
      1
    )
    ```
  - Place alongside existing "Avg Cost/Session" and "Cost/Active Hour" stats
  - Add time series variant using `increase()` for trend visibility
- **Effort**: Low

### 7. Add Project Comparison View

- **What**: A table or bar chart comparing cost, tokens, sessions, and LOC across projects side-by-side
- **Why**: The `$project` dropdown filters to one project at a time but there's no way to see **all projects compared** in one view. If you work on 5 repos, you want to know which one consumes the most budget
- **How**:
  - Add a horizontal bar chart panel:
    ```promql
    sort_desc(sum by (project) (increase(claude_code_cost_usage_USD_total[$__range])))
    ```
  - Add a table with columns: Project, Cost, Tokens, Sessions, LOC, Cost/LOC
  - Place in a new "Project Analytics" row (collapsed by default)
- **Effort**: Low

### 8. Add Prometheus Recording Rules for Common Aggregations

- **What**: Create a `recording-rules.yml` file with pre-aggregated metrics
- **Why**: Every dashboard query currently runs against raw metrics. The `session_id` label creates high cardinality — with 1000 sessions, queries like `sum(max_over_time(claude_code_cost_usage_USD_total[$__range]))` must scan all session_id series. Recording rules pre-compute aggregates at scrape time
- **How**:
  - Create `recording-rules.yml`:
    ```yaml
    groups:
      - name: claude_code_aggregates
        interval: 60s
        rules:
          - record: claude_code:cost_by_project:increase5m
            expr: sum by (project) (increase(claude_code_cost_usage_USD_total[5m]))
          - record: claude_code:tokens_by_project_model:increase5m
            expr: sum by (project, model) (increase(claude_code_token_usage_tokens_total[5m]))
          - record: claude_code:active_sessions
            expr: count(sum by (session_id) (rate(claude_code_cost_usage_USD_total[5m]) > 0))
    ```
  - Mount in `docker-compose.yml` and reference in `prometheus.yml` under `rule_files`
  - Migrate heavy dashboard queries to use pre-aggregated metrics
- **Effort**: Medium

### 9. Add Memory Limiter to OTEL Collector

- **What**: Add the `memory_limiter` processor to the OTEL Collector pipeline
- **Why**: The current processor pipeline (`batch`, `deltatocumulative`) has no memory bounds. If Claude Code emits a burst of telemetry (e.g., a long session with many tool calls), the collector can OOM and crash, losing all buffered data. The debug exporter (currently enabled) also adds memory/CPU overhead
- **How**:
  - In `otel-collector-config.yaml`:
    ```yaml
    processors:
      memory_limiter:
        check_interval: 1s
        limit_mib: 512
        spike_limit_mib: 128
      batch:
        timeout: 10s
        send_batch_size: 1024
    ```
  - Update pipeline: `processors: [memory_limiter, batch, deltatocumulative]`
  - Remove or disable the `debug` exporter in production
  - Add resource limits in `docker-compose.yml`: `mem_limit: 768m`
- **Effort**: Low

### 10. Improve "vs Prev" Panels for Edge Cases

- **What**: Fix the comparison panels (Cost vs Prev, Tokens vs Prev, Sessions vs Prev) to handle zero-previous-period gracefully
- **Why**: When the previous period has zero data (e.g., you start using Claude Code for the first time, or select a weekend vs weekday), the `clamp_min(..., 0.001)` denominator produces misleading percentages like "+999900.0%". The panels show "N/A" via `noValue` only when *current* data is missing, not when *previous* data is missing
- **How**:
  - Wrap the comparison expression in a conditional that returns `NaN` when previous period is truly zero:
    ```promql
    (sum(increase(metric[$__range] offset $__range)) > 0)
    and
    (current - previous) / previous * 100
    or vector(0) * NaN
    ```
  - Alternatively, add a text annotation: "No data in previous period" via value mappings when the result exceeds a reasonable threshold (e.g., >1000%)
- **Effort**: Low

---

## Low Priority / Nice-to-Have

### 11. Add "Model Recommendation" Insight Panel

- **What**: A text/stat panel that compares cost-per-output-token across models actually used, highlighting potential savings
- **Why**: Users may not realize they're using Opus ($75/M output) for tasks where Sonnet ($15/M output) would suffice. Showing "You could save $X by using Sonnet for sessions currently on Opus" is directly actionable
- **How**:
  - Calculate hypothetical Sonnet cost for Opus sessions:
    ```promql
    sum(increase(claude_code_token_usage_tokens_total{model=~".*opus.*", type="output"}[$__range])) * 15 / 1000000
    ```
  - Compare against actual Opus cost
  - Show the delta as "Potential savings: $X if Opus sessions used Sonnet"
  - Place in the Model Analytics section
- **Effort**: Medium (requires careful query design)

### 12. Add Tool Usage Success Rate Panel

- **What**: A time series showing tool success rate (%) over time, broken down by tool
- **Why**: The current "Tool Success / Failure" panel shows aggregate counts but not the **rate** over time. A sudden drop in success rate could indicate a configuration issue, permissions problem, or API change. The existing bar gauge is static — it doesn't show trends
- **How**:
  - LogQL query:
    ```logql
    sum by (tool_name)(count_over_time({service_name="claude-code"} | event_name="tool_result" | success="true" [$__auto]))
    /
    sum by (tool_name)(count_over_time({service_name="claude-code"} | event_name="tool_result" [$__auto]))
    * 100
    ```
  - Display as time series with Y-axis 0-100%
- **Effort**: Low

### 13. Add Hardcoded Model Pricing to Dashboard as Annotation or Variable

- **What**: Surface the pricing table used for cost calculations somewhere visible in the dashboard
- **Why**: Cost calculations use hardcoded pricing in `backfill-metrics.py` (Opus: $15/$75, Sonnet: $3/$15, Haiku: $0.80/$4 per 1M tokens). When Anthropic changes pricing or adds new models, the dashboard shows stale cost data with no indication. Users need to know what pricing assumptions underlie the numbers
- **How**:
  - Add a collapsed "Pricing Reference" row at the bottom of the dashboard with a text panel showing the current pricing table
  - Alternatively, add a dashboard annotation or description note
  - In the backfill script, add a `--pricing-file` flag to load pricing from YAML/JSON instead of hardcoding
- **Effort**: Low

### 14. Add Weekly/Monthly Summary Stat Row

- **What**: A row with stats pre-configured for fixed 7d and 30d windows regardless of the dashboard time range
- **Why**: The current dashboard stats are entirely driven by the time range selector. Users often want to see "this week's total" and "this month's total" at a glance without changing the time range. The "vs Prev" panels provide comparison but not fixed-window totals
- **How**:
  - Add stat panels with hardcoded ranges:
    ```promql
    sum(increase(claude_code_cost_usage_USD_total{project=~"$project"}[7d]))
    ```
    ```promql
    sum(increase(claude_code_cost_usage_USD_total{project=~"$project"}[30d]))
    ```
  - Place in a collapsed "Summary" row at the top, below the Overview row
- **Effort**: Low

---

## Reliability Concerns

Specific queries and configurations with identified issues:

1. **`loki-config.yaml:39`** — `retention_enabled: false` — logs grow unboundedly. This is the single most critical reliability issue.

2. **`loki-config.yaml:31-32`** — `ingestion_rate_mb: 50` is aggressive for a single-node Loki. If Promtail + backfill + OTEL all push simultaneously, Loki may reject with 429s and no one will know (no alerting).

3. **`otel-collector-config.yaml`** — The `debug` exporter is active in the metrics pipeline. This logs all metrics to stderr, adding CPU/memory overhead and filling Docker container logs.

4. **`docker-compose.yml`** — No `mem_limit` or `cpus` on any service. Prometheus in particular can consume unbounded memory during expensive queries across high-cardinality `session_id` labels.

5. **`claude-code.json` lines 578, 655** — The "Avg Cost/Session" and "Cost/Active Hour" panels use `max_over_time` for the numerator but this returns total accumulated cost only if the dashboard time range covers the entire session. For partial session overlap (session started before `$__from`), the value returned is the max within the visible range, not the session total. This creates a subtle inconsistency with the "Period Cost" panel which correctly uses `increase()`.

6. **`claude-code.json` line 1534** — The "Status" column in the Sessions table uses `> bool (time() - 300)` to mark sessions as "Active" if updated within 5 minutes. This 300s threshold is hardcoded and may mismatch Prometheus's `metric_expiration: 5m` in the OTEL collector config, creating a race condition where a session is marked "Active" but its metrics have already gone stale.

7. **`promtail-config.yaml`** — `session_id` is promoted to a Loki label (not just structured metadata). Each unique session creates a new Loki stream. At scale (1000+ sessions/month), this creates stream churn that impacts Loki's ingester and compactor performance. Consider moving `session_id` to structured metadata only.

8. **`claude-code.json` lines 2037, 2163** — The "Cost by Model" pie chart and bar chart use `max_over_time` while the "Model Breakdown" table uses `increase()` for Cost (line 2416). These will show **different numbers** for the same metric in the same time range, which is confusing. The pie/bar should also use `increase()` for consistency.

9. **`scripts/backfill-metrics.py` line 42** — Unknown models fall back to Sonnet pricing (`return MODEL_PRICING["claude-sonnet-4"]`). If a new model like `claude-5-opus` is used, it gets charged at Sonnet rates ($3/M input instead of $15+/M), massively understating actual cost.
