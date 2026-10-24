import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "orchestrator"))
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")

import redis  # noqa: E402


def _redis_up():
    try:
        return redis.Redis.from_url(os.environ["REDIS_URL"]).ping()
    except redis.exceptions.ConnectionError:
        return False


requires_redis = pytest.mark.skipif(not _redis_up(), reason="needs Redis at REDIS_URL")


@pytest.fixture
def adm():
    import admission

    admission.client().flushdb()
    yield admission
    admission.client().flushdb()
