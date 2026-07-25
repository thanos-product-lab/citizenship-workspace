"""Dump the FastAPI OpenAPI schema to stdout.

Used by `just api-client` and the CI drift check. Keys are sorted so the output
is deterministic and diffs are meaningful.
"""

import json

from app.main import app


def main() -> None:
    print(json.dumps(app.openapi(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
