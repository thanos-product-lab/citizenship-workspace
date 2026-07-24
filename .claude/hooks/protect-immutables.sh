#!/usr/bin/env bash
# PreToolUse guard. Blocks edits to files that must never be hand-modified.
# Exit 2 = block and surface stderr to Claude.
set -euo pipefail

payload="$(cat)"
path="$(printf '%s' "$payload" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("tool_input",{}).get("file_path",""))' 2>/dev/null || true)"
[ -z "$path" ] && exit 0

# 1. Generated API client — regenerate, never hand-edit.
case "$path" in
  */packages/api-client/*)
    echo "BLOCKED: packages/api-client is generated from the FastAPI OpenAPI schema." >&2
    echo "Change the FastAPI route or Pydantic schema, then run 'just api-client'." >&2
    exit 2 ;;
esac

# 2. Alembic migrations already committed. Forward-only in practice.
case "$path" in
  */migrations/versions/*.py)
    if [ -n "$(git log --oneline -1 -- "$path" 2>/dev/null)" ]; then
      echo "BLOCKED: $(basename "$path") is a committed migration." >&2
      echo "Migrations are forward-only. Add a new revision instead." >&2
      exit 2
    fi ;;
esac

# 3. Source-of-truth RFCs need a deliberate decision, not a drive-by edit.
case "$path" in
  *DETERMINISTIC_RULES_SPEC.md|*DOMAIN_MODEL_RFC.md)
    echo "BLOCKED: $(basename "$path") is a source-of-truth RFC." >&2
    echo "Propose the change and get it agreed first. Code follows the RFC," >&2
    echo "not the other way round (CLAUDE.md, precedence rule)." >&2
    exit 2 ;;
esac

exit 0
