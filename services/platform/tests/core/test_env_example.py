"""`.env.example` describes the settings that actually exist.

A template is documentation that rots silently: nothing fails when a setting is added
and the template is not updated, so the file drifts until it is misleading, and a
misleading template is worse than none — it is the thing someone copies when they are
new and least able to tell it is wrong.

It also has to live *here*, beside the file it templates. `Settings(env_file=".env")`
resolves relative to the working directory and both the API and the worker run from
`services/platform`, so a `.env` at the repository root is read by nothing. The
template spent M1-M8 slice 1 at the root, documenting backend variables for a file
that could never be loaded, and `cp .env.example .env` there did nothing at all.
"""

import pathlib
import re

from app.core.config import Settings

#: Beside `app/`, not above `services/`.
ENV_EXAMPLE = pathlib.Path(__file__).parent.parent.parent / ".env.example"

_ASSIGNMENT = re.compile(r"^([A-Z][A-Z0-9_]*)=")


def _documented() -> list[str]:
    return [
        match.group(1)
        for line in ENV_EXAMPLE.read_text().splitlines()
        if (match := _ASSIGNMENT.match(line))
    ]


def test_the_template_sits_beside_the_env_file_it_describes() -> None:
    assert ENV_EXAMPLE.is_file(), (
        f"{ENV_EXAMPLE} is missing. It must live in services/platform, because that is "
        "the working directory Settings resolves `.env` against — a template anywhere "
        "else describes a file nothing reads."
    )


def test_every_setting_is_documented() -> None:
    """Adding a setting without documenting it is the drift this catches."""
    documented = set(_documented())
    missing = sorted(
        name.upper() for name in Settings.model_fields if name.upper() not in documented
    )
    assert missing == [], (
        f"settings absent from .env.example: {missing}. A template that omits a setting "
        "sends someone to read the source to discover it exists."
    )


def test_the_template_names_no_setting_that_does_not_exist() -> None:
    """The more damaging direction: a typo, or a variable removed from `Settings` and
    left in the template. Either way the reader sets something with no effect and has
    no way to find out."""
    fields = set(Settings.model_fields)
    unknown = sorted(name for name in _documented() if name.lower() not in fields)
    assert unknown == [], (
        f".env.example names variables that are not settings: {unknown}. Setting one of "
        "these does nothing, silently."
    )


def test_the_template_carries_no_values_for_the_secrets() -> None:
    """A committed template must not ship a working credential, and must not ship a
    *plausible* one either — a placeholder that looks real gets deployed."""
    secrets = ("OPENAI_API_KEY", "CLERK_SECRET_KEY", "UPLOAD_TOKEN_SECRET", "AI_PROBE_SECRET")
    populated = [
        line
        for line in ENV_EXAMPLE.read_text().splitlines()
        if (match := _ASSIGNMENT.match(line))
        and match.group(1) in secrets
        and line.split("=", 1)[1].strip()
    ]
    assert populated == [], f"secrets given values in the committed template: {populated}"


def test_the_template_is_loadable_as_an_env_file(tmp_path: pathlib.Path) -> None:
    """`cp .env.example .env` has to produce a file the app can actually read. Catches
    a stray unquoted value or a broken line that only surfaces when someone follows
    the README."""
    target = tmp_path / ".env"
    target.write_text(ENV_EXAMPLE.read_text())
    settings = Settings(_env_file=target)  # type: ignore[call-arg]
    assert settings.service_name
    # And the defaults it ships are ones the boot checks accept.
    assert settings.ai_request_timeout_seconds <= settings.ai_task_deadline_seconds
    assert settings.ai_daily_spend_ceiling_usd > 0
