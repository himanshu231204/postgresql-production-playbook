import os
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    if "DATABASE_URL" not in os.environ:
        pytest.skip("DATABASE_URL not set; these tests need a PostgreSQL database")
    with TestClient(app) as test_client:  # runs the lifespan (engine create/dispose)
        yield test_client
