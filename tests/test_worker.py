import concurrent.futures
import json

import pytest

from conftest import requires_redis

pytestmark = requires_redis


@pytest.fixture
def worker(adm, monkeypatch):
    import worker as w

    calls = []
    monkeypatch.setattr(w, "classify_intent", lambda text: ["procurement"])
    monkeypatch.setattr(w, "discover_agent", lambda cap: {"url": f"http://{cap}"})

    def dispatch(agent, raw):
        calls.append(raw)
        return {"ok": True}

    monkeypatch.setattr(w, "dispatch", dispatch)
    w.calls = calls
    return w


def test_request_completes_and_releases_credit(worker, adm):
    assert worker.process_request("req-1", "buy 10 widgets") == "done"
    assert json.loads(adm.client().get("result:req-1"))["results"]["procurement"] == {"ok": True}
    assert adm.client().get("status:req-1") == "done"
    assert adm.current_budget() == adm.MAX_CONCURRENT_CALLS


def test_redelivery_after_completion_is_skipped(worker, adm):
    worker.process_request("req-2", "x")
    assert worker.process_request("req-2", "x") == "duplicate"
    assert len(worker.calls) == 1


def test_concurrent_duplicate_deliveries_run_once(worker, adm):
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
        outcomes = list(ex.map(lambda _: worker.process_request("req-3", "x"), range(3)))
    assert sorted(outcomes) == ["done", "duplicate", "duplicate"]
    assert len(worker.calls) == 1
    assert adm.current_budget() == adm.MAX_CONCURRENT_CALLS


def test_failed_attempt_can_be_retried(worker, adm, monkeypatch):
    """Previously the claim was kept after a failure, so the redelivered
    message was skipped as a duplicate and the request never completed."""
    def boom(text):
        raise ConnectionError("LLM unavailable")

    monkeypatch.setattr(worker, "classify_intent", boom)
    with pytest.raises(ConnectionError):
        worker.process_request("req-4", "x")
    assert adm.current_budget() == adm.MAX_CONCURRENT_CALLS  # credit released

    monkeypatch.setattr(worker, "classify_intent", lambda text: ["procurement"])
    assert worker.process_request("req-4", "x") == "done"


def test_no_capacity_rejects_and_records_error(worker, adm, monkeypatch):
    for i in range(adm.MAX_CONCURRENT_CALLS):
        adm.try_acquire_credit(f"busy{i}")
    monkeypatch.setattr(worker, "acquire_credit", lambda holder, timeout_seconds: None)
    assert worker.process_request("req-5", "x") == "rejected"
    assert "capacity" in json.loads(adm.client().get("result:req-5"))["error"]
