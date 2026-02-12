# Napkin

## Corrections
| Date | Source | What Went Wrong | What To Do Instead |
|------|--------|----------------|-------------------|
| 2026-02-12 | self | Tried a large multi-hunk `apply_patch` on a big JSON file and it failed to match | Break large JSON edits into smaller, focused patches |
| 2026-02-12 | self | Added a comment and left a trailing comma in JSON, breaking parsing | Never add comments in JSON and re-check commas after removing blocks |

## User Preferences
- (accumulate here as you learn them)

## Patterns That Work
- For Grafana table panels in `claude-code.json`, using `merge` -> `organize` -> `calculateField` -> `organize` gives stable column naming/order and makes derived metrics (like acceptance rate) straightforward.

## Patterns That Don't Work
- (approaches that failed and why)

## Domain Notes
- (project/domain context that matters)
- Loki labels in this stack are assigned at promtail ingestion time; changing label extraction does not backfill historical streams, so panel fixes may only appear on newly ingested logs.
