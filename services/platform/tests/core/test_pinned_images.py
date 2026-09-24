"""The MinIO server CI and Compose run, and the three times its source went away.

Not a unit test of anything in `app/`. It reads files at the repository root and asserts
they agree, because the failure it guards is the one a test suite cannot otherwise see: a
storage behaviour differing between a green local run and a red CI one, with nothing in the
diff to explain it.

**Three upstream sources have dropped this server out from under the build.** First
`bitnami/minio`, whose repository went to zero tags when Bitnami moved everything to
`bitnamilegacy/`. Then `docker.io/minio/minio`, which in September 2026 stopped serving any
tag. Then `quay.io/minio/minio` and the `dl.min.io` binaries, which by late September 2026
answered 401 and 410 Gone for every release: MinIO no longer distributes the community
server except as source. Each time the break showed in CI first, because CI pulls fresh and a
developer machine keeps its cache.

So the server is now **built from its source tag**, in `infra/docker/minio.Dockerfile`, by
both Compose and CI. That file is the only place the release is pinned, and these tests keep
it that way: both sides build it, neither pulls a MinIO image from a registry, neither
overrides the pin, and the pin is a real release.
"""

import pathlib
import re

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
COMPOSE = REPO_ROOT / "docker-compose.yml"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
DOCKERFILE = REPO_ROOT / "infra" / "docker" / "minio.Dockerfile"


def _require(path: pathlib.Path) -> str:
    if not path.is_file():  # pragma: no cover - only if the repo layout moves
        pytest.skip(f"{path} not found; this test reads the repository, not the package")
    return path.read_text(encoding="utf-8")


def _code(text: str) -> str:
    """The file without its comments, so a history note naming an old registry is not
    mistaken for a reference to it."""
    return "\n".join(line.split("#", 1)[0] for line in text.splitlines())


def test_compose_and_ci_build_the_same_dockerfile() -> None:
    """One Dockerfile for both sides, so they cannot run different servers."""
    compose = _code(_require(COMPOSE))
    workflow = _code(_require(WORKFLOW))

    assert re.search(r"dockerfile:\s*minio\.Dockerfile", compose), (
        "docker-compose.yml does not build infra/docker/minio.Dockerfile"
    )
    assert re.search(r"file:\s*infra/docker/minio\.Dockerfile", workflow), (
        "ci.yml does not build infra/docker/minio.Dockerfile"
    )


def test_neither_side_pulls_a_minio_image_from_a_registry() -> None:
    """Every published MinIO image is gone; a reference to one is a build that will fail."""
    for path in (COMPOSE, WORKFLOW):
        code = _code(_require(path))
        pulled = re.findall(r"(?:quay\.io/|docker\.io/|bitnami/)?minio/minio:\S+", code)
        assert not pulled, f"{path.name} pulls {pulled}; MinIO no longer publishes images"


def test_neither_side_overrides_the_pinned_release() -> None:
    """The Dockerfile's default is the pin. A build argument on one side would quietly make
    that side a different server."""
    for path in (COMPOSE, WORKFLOW):
        assert "MINIO_RELEASE" not in _code(_require(path)), (
            f"{path.name} overrides MINIO_RELEASE; the pin must live only in the Dockerfile"
        )


def test_the_dockerfile_pins_a_release_tag() -> None:
    """Not `master`, not a branch: a tag, so the same source builds the same server."""
    match = re.search(r"^ARG MINIO_RELEASE=(\S+)$", _require(DOCKERFILE), re.MULTILINE)
    assert match, "infra/docker/minio.Dockerfile does not pin MINIO_RELEASE"
    assert match.group(1).startswith("RELEASE."), f"{match.group(1)} is not a MinIO release tag"
