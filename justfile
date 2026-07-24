# Cross-language command runner for citizenship-workspace.
#
# Most recipes are stubs until their milestone lands — keep this file in sync
# with CLAUDE.md §5 as the real toolchain is wired up in M1. Recipes below that
# are not yet implemented should still exist and exit cleanly so hooks and CI do
# not error before their milestone.

# Hypothesis property suite for the deterministic rules (DETERMINISTIC_RULES_SPEC.md §10).
# Relied on by .claude/hooks/rules-guard.sh and the milestone gates. Exits 0 when
# the rule tests do not exist yet (pre-M3B) so the PostToolUse hook does not error.
test-rules:
    @if [ -d services/platform/tests/rules ]; then \
        cd services/platform && uv run pytest tests/rules -m property -q; \
    else \
        echo "test-rules: services/platform/tests/rules not present yet (pre-M3B); skipping."; \
    fi
