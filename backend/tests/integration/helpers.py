import os

import pytest


def require_test_database_url() -> str:
    test_database_url = os.environ.get("TEST_DATABASE_URL")
    if not test_database_url:
        pytest.fail("TEST_DATABASE_URL is required for integration tests. "
                    "Run unit tests with `uv run pytest tests/unit`, or start PostgreSQL "
                    "and set TEST_DATABASE_URL for integration tests.")
    return test_database_url
