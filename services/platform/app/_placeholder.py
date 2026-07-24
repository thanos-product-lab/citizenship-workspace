"""Placeholder so strict type-checking, linting, and tests have a target.

Real modules (health endpoints in M1 slice 2, then the domain modules) replace
this. It exists only to prove the backend toolchain runs end to end.
"""


def scaffold_ready() -> bool:
    """Trivial typed function proving mypy, ruff, and pytest have something to run."""
    return True
