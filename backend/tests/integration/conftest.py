import os

os.environ.setdefault("MONGODB_DATABASE", "job_agent_integration_test")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from pymongo import MongoClient  # noqa: E402
from pymongo.errors import PyMongoError  # noqa: E402

from app.config import settings  # noqa: E402


def _mongo_available() -> bool:
    try:
        MongoClient(settings.mongodb_url, serverSelectionTimeoutMS=1500).admin.command("ping")
        return True
    except PyMongoError:
        return False


@pytest.fixture(scope="session", autouse=True)
def require_mongo():
    if _mongo_available():
        return
    if os.getenv("REQUIRE_INTEGRATION") == "1":
        pytest.fail(f"MongoDB is required for integration tests but is unreachable at {settings.mongodb_url}")
    pytest.skip("MongoDB not reachable; integration tests skipped (set REQUIRE_INTEGRATION=1 to fail instead)")


@pytest.fixture()
def client():
    MongoClient(settings.mongodb_url).drop_database(settings.mongodb_database)
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client
