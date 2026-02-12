---
name: no-heredoc-commit
enabled: true
event: bash
pattern: git\s+commit.*<<
action: warn
---

**Do not use heredoc syntax in git commit commands.**

The sandbox blocks temp file creation, so `cat <<'EOF'` will fail with "operation not permitted".

Use a plain `-m` string instead:
```
git commit -m "Title

Body line 1
Body line 2

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

For multiline messages, use literal `\n` or pass the message directly in quotes.
