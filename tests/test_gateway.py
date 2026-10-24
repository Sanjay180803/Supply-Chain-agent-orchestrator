import importlib
import os
import sys

import pytest
from fastapi.testclient import TestClient

from conftest import requires_redis

pytestmark = requires_redis

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "gateway"))


class InstantWorkerProducer:
    """Simulates a worker that finishes before send() returns."""

    def __init__(self, r):
        self.r = r

    def send(self, topic, payload):
        self.r.set(f"status:{payload['request_id']}", "done")
        self.r.set(f"result:{payload['request_id']}", '{"ok": true}')
        return self

    def get(self, timeout=None):
        return None


class FailingProducer:
    def send(self, topic, payload):
        raise RuntimeError("broker down")


@pytest.fixture
def gw(adm, monkeypatch):
    main = importlib.import_module("main")
    monkeypatch.setattr(main, "r", adm.client())
    return main


def test_fast_worker_result_is_not_overwritten(gw, monkeypatch):
    monkeypatch.setattr(gw, "get_producer", lambda: InstantWorkerProducer(gw.r))
    client = TestClient(gw.app)
    rid = client.post("/submit", json={"request": "x"}).json()["request_id"]
    assert client.get(f"/result/{rid}").json() == {"status": "done", "result": {"ok": True}}


def test_publish_failure_leaves_no_status(gw, monkeypatch):
    monkeypatch.setattr(gw, "get_producer", lambda: FailingProducer())
    body = TestClient(gw.app).post("/submit", json={"request": "x"}).json()
    assert "error" in body
    assert not list(gw.r.scan_iter("status:*"))


def test_unknown_request(gw):
    assert TestClient(gw.app).get("/result/nope").json() == {"error": "unknown request_id"}
