"""The container images CI and Compose agree on, and the two times they stopped existing.

Not a unit test of anything in `app/`. It reads two files at the repository root and
asserts they say the same thing, because the failure it guards is the one a test suite
cannot otherwise see: a storage behaviour differing between a green local run and a red CI
one, with nothing in the diff to explain it.

**Twice now an upstream registry has dropped this image out from under the build.** First
`bitnami/minio`, whose repository went to zero tags when Bitnami moved everything to
`bitnamilegacy/`. Then `docker.io/minio/minio`, which in September 2026 stopped serving
*any* tag — `docker pull minio/minio:latest` answers "repository does not exist or may
require 'docker login'". Pinning the tag did not help, because the repository went, not
the tag.

The second one was invisible locally: `just up` kept working from a layer cached a year
earlier, so only CI — which pulls fresh every run — went red, and the error read as a CI
problem rather than an upstream one. That asymmetry is the reason the registry is written
out explicitly in both files rather than left to the `docker.io` default.
"""

import pathlib
import re

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
COMPOSE = REPO_ROOT / "docker-compose.yml"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"


def _require(path: pathlib.Path) -> str:
    if not path.is_file():  # pragma: no cover - only if the repo layout moves
        pytest.skip(f"{path} not found; this test reads the repository, not the package")
    return path.read_text(encoding="utf-8")


def test_compose_and_ci_pin_the_same_minio_image() -> None:
    """Identical reference, registry and tag included.

    Compared as whole strings rather than by tag alone. A tag match with a registry
    mismatch is exactly the state this file exists to prevent — and is what the codebase
    was in for the hour between Docker Hub dropping the image and CI being told.
    """
    compose = _require(COMPOSE)
    workflow = _require(WORKFLOW)

    compose_image = re.search(r"^\s*image:\s*(\S*minio\S*)\s*$", compose, re.MULTILINE)
    ci_image = re.search(r"^\s*MINIO_IMAGE:\s*(\S+)\s*$", workflow, re.MULTILINE)

    assert compose_image, "no minio image found in docker-compose.yml"
    assert ci_image, "no MINIO_IMAGE found in ci.yml"
    assert compose_image.group(1) == ci_image.group(1), (
        f"compose runs {compose_image.group(1)}, CI runs {ci_image.group(1)}. The storage "
        "security tests are the only place that can assert a bucket is private or a URL "
        "expires, and two different images can answer those differently."
    )


def test_the_minio_image_names_its_registry_and_pins_a_tag() -> None:
    """Neither half is optional.

    A bare `minio/minio:TAG` resolves to whatever `docker.io` currently serves — which as
    of September 2026 is nothing. A `:latest` on either side resolves to whenever each
    machine last pulled. Both failure modes present as "works here, red in CI".
    """
    image = re.search(r"^\s*MINIO_IMAGE:\s*(\S+)\s*$", _require(WORKFLOW), re.MULTILINE)
    assert image
    reference = image.group(1)

    assert reference.count("/") >= 2 and "." in reference.split("/")[0], (
        f"{reference} does not name a registry; it will resolve against docker.io, which "
        "no longer serves this repository"
    )
    tag = reference.rsplit(":", 1)[-1]
    assert tag != "latest", "a moving tag is how the two sides drift apart unnoticed"
    assert tag.startswith("RELEASE."), f"{tag} is not a MinIO release tag"
