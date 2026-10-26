import os
import shutil
import subprocess
import time
from pathlib import Path
from urllib.parse import urlparse

# Never use the application database. Unit tests may import settings before this
# file runs, so the name is assigned onto the settings object below as well.
os.environ["MONGODB_DATABASE"] = "job_agent_integration_test"

import pytest  # noqa: E402
import redis  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from pymongo import MongoClient  # noqa: E402
from pymongo.errors import PyMongoError  # noqa: E402

from app.config import settings  # noqa: E402

settings.mongodb_database = "job_agent_integration_test"

_TEST_REDIS_CONTAINER = "job-agent-integration-redis"
_started_test_redis = False


def _mongo_available() -> bool:
    try:
        MongoClient(settings.mongodb_url, serverSelectionTimeoutMS=1500).admin.command("ping")
        return True
    except PyMongoError:
        return False


def _redis_reachable(url: str) -> bool:
    try:
        client = redis.Redis.from_url(url, socket_connect_timeout=1, socket_timeout=1)
        return client.ping() is True
    except Exception:
        return False


def _docker_executable() -> str | None:
    found = shutil.which("docker")
    if found:
        return found
    candidate = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Docker" / "Docker" / "resources" / "bin" / "docker.exe"
    return str(candidate) if candidate.exists() else None


def _start_isolated_redis(port: int) -> None:
    """Start Redis for this test process only, bound to loopback. Does not publish the Compose Redis."""
    global _started_test_redis
    docker = _docker_executable()
    if docker is None:
        raise RuntimeError("Redis is not reachable and Docker is not available to start an isolated test Redis")
    subprocess.run([docker, "rm", "-f", _TEST_REDIS_CONTAINER], check=False, capture_output=True, text=True)
    started = subprocess.run(
        [
            docker,
            "run",
            "-d",
            "--rm",
            "--name",
            _TEST_REDIS_CONTAINER,
            "-p",
            f"127.0.0.1:{port}:6379",
            "redis:7-alpine",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if started.returncode != 0:
        detail = (started.stderr or started.stdout or "").strip()
        raise RuntimeError(f"Could not start isolated test Redis on 127.0.0.1:{port}: {detail}")
    _started_test_redis = True


def _stop_isolated_redis() -> None:
    global _started_test_redis
    if not _started_test_redis:
        return
    docker = _docker_executable()
    if docker is not None:
        subprocess.run([docker, "rm", "-f", _TEST_REDIS_CONTAINER], check=False, capture_output=True, text=True)
    _started_test_redis = False


@pytest.fixture(scope="session", autouse=True)
def require_mongo():
    if _mongo_available():
        yield
        return
    if os.getenv("REQUIRE_INTEGRATION") == "1":
        pytest.fail(f"MongoDB is required for integration tests but is unreachable at {settings.mongodb_url}")
    pytest.skip("MongoDB not reachable; integration tests skipped (set REQUIRE_INTEGRATION=1 to fail instead)")


def _use_ipv4_loopback(url: str) -> str:
    """localhost may resolve to IPv6 on Windows. The test Redis listens on 127.0.0.1 only."""
    parsed = urlparse(url)
    if parsed.hostname != "localhost":
        return url
    return url.replace("://localhost", "://127.0.0.1", 1)


@pytest.fixture(scope="session", autouse=True)
def require_redis():
    """Use a real Redis. CI provides 127.0.0.1:6379. Otherwise start a loopback-only container."""
    settings.redis_url = _use_ipv4_loopback(settings.redis_url)
    url = settings.redis_url
    parsed = urlparse(url)
    host = parsed.hostname or ""
    port = parsed.port or 6379
    if host not in {"localhost", "127.0.0.1"}:
        pytest.fail(f"Integration tests need a reachable Redis at {url}. Refusing to publish a non-local address.")
    if not _redis_reachable(url):
        try:
            _start_isolated_redis(port)
        except RuntimeError as exc:
            pytest.fail(str(exc))
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if _redis_reachable(url):
                break
            time.sleep(0.5)
        else:
            _stop_isolated_redis()
            pytest.fail(f"Isolated test Redis on 127.0.0.1:{port} did not accept connections")
    try:
        yield
    finally:
        _stop_isolated_redis()


@pytest.fixture()
def client():
    MongoClient(settings.mongodb_url).drop_database(settings.mongodb_database)
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client
