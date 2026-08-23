"""The guard on the guard.

`minio_storage` fails rather than skips when a live store was promised, which covers an
unreachable MinIO. It cannot cover the case where the marked tests were never collected
at all — a renamed marker, a deleted file, a `-k` filter that quietly excluded them. A
fixture that never runs raises nothing.

So this asserts the marked tests exist in the run. It is the storage twin of
`test_the_check_has_routes_to_check`: an assertion that the thing doing the asserting
had anything to assert about.
"""

import pytest

from tests.evidence import conftest


@pytest.mark.skipif(
    not conftest.minio_is_expected(), reason="storage security tests are optional here"
)
def test_storage_integration_tests_actually_ran() -> None:
    # Read through the module rather than importing the name: `from … import count`
    # binds the value at import time, which is before the collection hook has run. The
    # first draft did exactly that and asserted 0 > 0 while the tests it was guarding
    # had all passed — a guard that fails closed, but for the wrong reason.
    assert conftest.collected_minio_tests > 0, (
        "CW_EXPECT_MINIO is set but no `minio`-marked tests were collected. A skipped "
        "security test reports green, which is worse than a missing one — the storage "
        "privacy, expiry and post-deletion assertions live only in test_storage_minio.py."
    )
