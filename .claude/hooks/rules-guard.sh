#!/usr/bin/env bash
# PostToolUse. Cheap greps for known-dangerous patterns, plus the invariant
# tests when rule code changes. Warnings only — never blocks.
set -uo pipefail

payload="$(cat)"
path="$(printf '%s' "$payload" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("tool_input",{}).get("file_path",""))' 2>/dev/null || true)"
[ -z "$path" ] && exit 0

warn() { echo "WARN $*" >&2; }

if [ -f "$path" ]; then
  case "$path" in
    *.py|*.ts|*.tsx)
      # The off-by-one. Window arithmetic without +1 day is the single most
      # consequential bug in this codebase (RULES_SPEC section 3).
      if grep -qE 'relativedelta\(years=[0-9]+\)' "$path" 2>/dev/null \
         && ! grep -qE 'timedelta\(days=1\)|days=1' "$path" 2>/dev/null; then
        warn "$path: year arithmetic with no +1 day adjustment."
        warn "  Windows are application_date - N years + 1 day (RULES_SPEC 3)."
      fi
      # Summation over per-trip counts breaks the monotonicity invariant.
      if grep -qiE 'sum\([^)]*absen' "$path" 2>/dev/null; then
        warn "$path: totals must be |union of date sets|, not a sum (RULES_SPEC 5.2)."
      fi
      ;;
  esac

  # No readiness score, anywhere, ever.
  if grep -qiE 'readiness_(score|percent)|percent_ready|readinessScore' "$path" 2>/dev/null; then
    warn "$path: readiness percentages are prohibited (CLAUDE.md 2.6)."
  fi

  # Frontend must not recompute server-owned totals.
  case "$path" in
    */apps/web/*)
      if grep -qE 'absence(Total|Days)[^=]*=[^=]*(reduce|filter)' "$path" 2>/dev/null; then
        warn "$path: calculations are server-side. Render the API breakdown."
      fi ;;
  esac
fi

# Run the invariant tests when rule code changes.
case "$path" in
  */app/assessments/*|*/app/residence/*|*/app/requirements/*|*/app/facts/*)
    if command -v just >/dev/null 2>&1; then
      echo "Rule code changed - running property tests..." >&2
      just test-rules 2>&1 | tail -30 >&2 || warn "Property tests failed."
    fi ;;
esac

exit 0
