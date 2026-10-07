import json
import sys

import httpx
import pytest

from skillrelay.instrumentation import Recorder
from skillrelay.models import Event
from skillrelay.safety import clean
from skillrelay.service import Service
from skillrelay.worker import drive


def test_json_and_nested_secret_redaction():
    assert "supersecret" not in str(clean({"api_key": "supersecret"}))
    assert "supersecret" not in clean('{"api_key": "supersecret"}')
    assert "supersecret" not in clean("password=supersecret")


def test_spool_replays_same_event_after_network_failure(tmp_path):
    recorder = Recorder("http://localhost", "private", spool=tmp_path)
    seen = []

    def failing(request):
        seen.append(json.loads(request.content))
        raise httpx.ConnectError("offline")

    recorder.client.close()
    recorder.client = httpx.Client(
        transport=httpx.MockTransport(failing), base_url="http://localhost"
    )
    with pytest.raises(httpx.ConnectError):
        recorder.event("run", "password=supersecret", "Observed")
    pending = list(tmp_path.glob("*.json"))
    assert len(pending) == 1 and "supersecret" not in pending[0].read_text()

    def success(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={})

    recorder.client = httpx.Client(
        transport=httpx.MockTransport(success), base_url="http://localhost"
    )
    recorder.flush()
    assert seen[0] == seen[1]
    assert not list(tmp_path.glob("*.json"))
    recorder.close()


def test_trusted_outcome_cannot_be_self_asserted(tmp_path):
    service = Service(tmp_path / "db")
    run = service.start("worker", "case", "Check result")
    event = service.event("worker", run["id"], Event(event_id="a", action="Check output"))
    service.finish("worker", run["id"], "pass")
    with pytest.raises(PermissionError):
        service.outcome_check("worker", run["id"], "pass", [event["id"]], "v1")
    service.set_policy("human", "human", trusted_evaluators=["checker"])
    result = service.outcome_check("checker", run["id"], "pass", [event["id"]], "v1")
    assert result["outcome_source"] == "external_evaluator:checker"


def test_driver_is_bounded_and_does_not_invoke_a_shell(tmp_path):
    service = Service(tmp_path / "db")
    with pytest.raises(ValueError):
        drive(service, ["echo", "missing prompt"], once=True)
    assert drive(service, [sys.executable, "-c", "pass", "{prompt}"], once=True) == 0
    run = service.start("worker", "case", "Check")
    service.finish("worker", run["id"], "unknown")
    assert drive(service, [sys.executable, "-c", "pass", "{prompt}"], once=True) == 1


def test_lease_renewal_ownership_and_ceiling(tmp_path):
    service = Service(tmp_path / "db")
    run = service.start("worker", "case", "Check")
    service.finish("worker", run["id"], "unknown")
    job = service.claim("learner")
    assert "claimed_at" in job
    with pytest.raises(ValueError):
        service.renew("stranger", job["id"], job["token"])
    result = service.renew("learner", job["id"], job["token"])
    assert result["lease_until"] <= job["claimed_at"] + 600


def test_future_database_version_is_not_silently_downgraded(tmp_path):
    import sqlite3

    path = tmp_path / "future.db"
    with sqlite3.connect(path) as db:
        db.execute("PRAGMA user_version=99")
    with pytest.raises(ValueError, match="schema version"):
        Service(path)
