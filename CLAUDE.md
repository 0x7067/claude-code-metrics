# CLAUDE.md — claude-code-metrics

## AI Agent

This repo has a persistent AI agent (via agent-as-repo) that knows the codebase. Run from the `agent-as-repo` directory:

```bash
# Ask a question
pnpm repo-expert ask claude-code-metrics "How does the backfill script work?"

# Onboarding walkthrough
pnpm repo-expert onboard claude-code-metrics

# Check agent health
pnpm repo-expert status --repo claude-code-metrics
```
