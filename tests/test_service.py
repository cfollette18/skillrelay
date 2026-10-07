import time

import pytest

from skillrelay.models import Assessment, Event, Proposal
from skillrelay.service import Service


@pytest.fixture
def service(tmp_path):
    return Service(tmp_path / "db.sqlite")


def propose(service, verified=False, title="Check before retry"):
    run = service.start("worker", "repair", "Repair a failed request")
    event = service.event(
        "worker", run["id"], Event(event_id="1", action="Check response code", result="429")
    )
    service.finish("worker", run["id"], "pass", "pass")
    if verified:
        service.verify_outcome("human", run["id"], "pass")
    # Latest verified job, if present, must actually be used.
    job = service.claim("learner")
    if verified:
        service.finish_job("learner", job["id"], job["token"], "no_change", "Use verified snapshot")
        job = service.claim("learner")
    proposal = Proposal(
        title=title,
        summary="Check response before retrying",
        applicability=["rate limiting"],
        steps=[{"instruction": "Inspect status first", "evidence": [event["id"]]}],
        checks=["Response has a status code"],
        dependencies={"api": "v1"},
    )
    version = service.propose("learner", job["id"], job["token"], proposal)
    return version


def evaluate(service, actor="evaluator"):
    job = service.claim(actor, "evaluate")
    return service.evaluate(
        actor,
        job["id"],
        job["token"],
        Assessment(
            support=4,
            applicability=4,
            completeness=4,
            contradictions=4,
            verdict="pass",
            rationale="Each instruction is supported by the observed response",
            evaluator_version="rubric-v1",
            evidence=[job["evidence"]["events"][0]["id"]],
        ),
    )


def test_human_mode_enforced_even_high_confidence(service):
    service.set_policy("human", "human", trusted_evaluators=["evaluator"])
    propose(service, verified=True)
    version = evaluate(service)
    assert version["confidence"] == 100
    assert version["state"] == "pending_review"
    assert not service.discover("worker", "repair")
    with pytest.raises(ValueError):
        service.review("human", version["id"], "wrong-hash", "approve")
    service.review("human", version["id"], version["hash"], "approve")
    assert len(service.discover("worker", "repair")) == 1


def test_automatic_confidence_and_provenance(service):
    service.set_policy("human", "automatic", trusted_evaluators=["evaluator"])
    propose(service)
    v = evaluate(service)
    assert v["confidence"] == 80 and v["state"] == "pending_review"
    propose(service, verified=True, title="Verified response handling")
    assert evaluate(service)["state"] == "active"


def test_activation_reads_current_policy(service):
    service.set_policy("human", "automatic", trusted_evaluators=["evaluator"])
    propose(service, verified=True)
    service.set_policy("human", "human")
    assert evaluate(service)["state"] == "pending_review"


def test_separate_evaluator_and_untrusted_fallback(service):
    service.set_policy("human", "automatic")
    propose(service, verified=True)
    assert service.claim("learner", "evaluate")["job"] is None
    assert evaluate(service)["state"] == "pending_review"


def test_idempotency_ownership_redaction_causality(service):
    run = service.start("worker", "task", "goal")
    event = Event(event_id="a", action="password=secret", result="Bearer abcdef1234")
    first = service.event("worker", run["id"], event)
    assert first == service.event("worker", run["id"], event)
    assert "secret" not in str(first)
    with pytest.raises(ValueError):
        service.event("worker", run["id"], Event(event_id="a", action="different"))
    with pytest.raises(PermissionError):
        service.event("other", run["id"], event)
    with pytest.raises(ValueError):
        service.event(
            "worker", run["id"], Event(event_id="b", action="handoff", causes=["missing"])
        )
    a = service.finish("worker", run["id"], "unknown")
    b = service.finish("worker", run["id"], "unknown")
    assert a["job"] == b["job"]


def test_expired_lease_and_restart(service):
    run = service.start("worker", "task", "goal")
    service.finish("worker", run["id"], "unknown")
    job = service.claim("first")
    with service.store.connect() as db:
        stored = service.store.get(db, "job", job["id"])
        stored["lease_until"] = time.time() - 1
        service.store.put(db, "job", job["id"], stored)
    restarted = Service(service.store.path)
    new = restarted.claim("second")
    assert new["id"] == job["id"] and new["token"] != job["token"]
    with pytest.raises(ValueError):
        restarted.finish_job("first", job["id"], job["token"], "no_change", "stale")
    restarted.finish_job("second", new["id"], new["token"], "no_change", "done")
    assert "token" not in restarted.snapshot()["job"][0]


def test_compatibility_and_revocation(service):
    propose(service)
    v = evaluate(service)
    service.review("human", v["id"], v["hash"], "approve")
    assert service.get_skill("worker", v["id"])
    service.dependency("human", "api", "v2")
    assert not service.discover("worker", "repair")
    with pytest.raises(ValueError):
        service.review("human", v["id"], v["hash"], "rollback")
