"""Building the configured provider, once per process.

Separate from `provider.py` so that module stays a pure adapter with no opinion
about settings — which is what lets a test construct an `OpenAIProvider` around a
stub client without touching the environment.
"""

from functools import lru_cache

from app.ai.fake import FakeProvider
from app.ai.provider import AIProvider, OpenAIProvider
from app.core.config import get_settings


@lru_cache
def get_provider() -> AIProvider:
    """The process's provider. Cached because the OpenAI client holds a connection
    pool, and building one per call would open a new pool per document."""
    settings = get_settings()
    if settings.ai_provider == "fake":
        # Reachable only in local environments; `check_ai_configuration` refuses to
        # boot elsewhere with this set.
        return FakeProvider()

    from openai import OpenAI

    # `max_retries=0`: retrying is `provider.py`'s decision, because only it knows
    # which failures are terminal. Leaving the SDK's own retries on would multiply
    # the attempt cap by the SDK's default and quietly retry the exhausted-credit
    # case the M8 spike found (AI_SPIKE_FINDINGS §5) — three attempts becoming nine
    # requests, none of which could have succeeded.
    return OpenAIProvider(OpenAI(api_key=settings.openai_api_key or None, max_retries=0))
