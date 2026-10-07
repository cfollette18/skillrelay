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


def test_automatic_confidence_and_provenance(service, tmp_path):
    service.set_policy("human", "automatic", trusted_evaluators=["evaluator"])
    propose(service)
    v = evaluate(service)
    assert v["confidence"] == 80 and v["state"] == "pending_review"
    service = Service(tmp_path / "verified.db")
    service.set_policy("human", "automatic", trusted_evaluators=["evaluator"])
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


@pytest.mark.parametrize(
    "pattern", ["sequential", "parallel", "group_chat", "handoff", "manager_worker", "graph"]
)
def test_workflow_patterns_and_causal_edges(service, pattern):
    root = service.start("manager", "case", "Coordinate", pattern=pattern, role="manager")
    child = service.start(
        "worker",
        "case",
        "Execute",
        workflow_id=root["workflow_id"],
        parent=root["id"],
        role="specialist",
    )
    first = service.event(
        "manager",
        root["id"],
        Event(event_id="a", kind="handoff", action="Delegate task", recipient="worker"),
    )
    service.event(
        "worker", child["id"], Event(event_id="b", action="Completed task", causes=[first["id"]])
    )
    with pytest.raises(PermissionError):
        service.finish("worker", child["id"], "pass", "pass")
    service.finish("worker", child["id"], "pass")
    service.finish("manager", root["id"], "fail", "fail")
    state = service.snapshot()
    assert state["workflow"][0]["outcome"] == "fail"
    assert next(r for r in state["run"] if r["id"] == child["id"])["outcome"] == "pass"
    assert state["event"][1]["causes"] == [first["id"]]


def test_late_evidence_blocks_previously_approved_skill(service):
    propose(service)
    v = evaluate(service)
    service.review("human", v["id"], v["hash"], "approve")
    run = service.snapshot()["run"][0]
    service.event(
        "worker",
        run["id"],
        Event(event_id="late", kind="failure", action="Discovered missing precondition"),
    )
    assert not service.discover("worker", "repair")
    with pytest.raises(ValueError):
        service.review("human", v["id"], v["hash"], "approve")
    assert len([j for j in service.snapshot()["job"] if j["kind"] == "distill"]) == 2


def test_hard_check_cannot_be_overridden(service):
    run = service.start("worker", "test", "Test")
    service.event("worker", run["id"], Event(event_id="a", action="Observed fact"))
    service.finish("worker", run["id"], "pass")
    j = service.claim("learner")
    v = service.propose(
        "learner",
        j["id"],
        j["token"],
        Proposal(
            title="Unsupported instruction",
            summary="Invalid citation",
            applicability=["test"],
            steps=[{"instruction": "Do something unsupported", "evidence": ["invented"]}],
            checks=["check"],
        ),
    )
    evaluate(service)
    with pytest.raises(ValueError):
        service.review("human", v["id"], v["hash"], "approve")


def test_revision_diff_and_rollback(service):
    v1 = propose(service)
    v1 = evaluate(service)
    service.review("human", v1["id"], v1["hash"], "approve")
    run = service.start("worker", "repair", "Observe another response")
    event = service.event(
        "worker", run["id"], Event(event_id="a", action="Read Retry-After header")
    )
    service.finish("worker", run["id"], "pass")
    j = service.claim("learner")
    data = {
        **v1["data"],
        "decision": "revise",
        "skill_id": v1["skill_id"],
        "steps": [{"instruction": "Inspect Retry-After", "evidence": [event["id"]]}],
    }
    v2 = service.propose("learner", j["id"], j["token"], Proposal(**data))
    v2 = evaluate(service)
    assert v2["number"] == 2
    assert "Inspect Retry-After" in service.diff(v1["id"], v2["id"])
    service.review("human", v2["id"], v2["hash"], "approve")
    assert service.discover("worker", "repair")[0]["id"] == v2["id"]
    service.review("human", v1["id"], v1["hash"], "rollback")
    assert service.discover("worker", "repair")[0]["id"] == v1["id"]
    assert service.snapshot()["version"][0]["data"] == v1["data"]


def test_agent_cannot_keep_human_provenance_after_changing_outcome(service):
    run = service.start("worker", "repair", "Observe")
    service.finish("worker", run["id"], "pass")
    service.verify_outcome("human", run["id"], "pass")
    service.finish("worker", run["id"], "fail")
    assert service.snapshot()["run"][0]["outcome_source"] == "self_report"


def test_human_deferral_blocks_inflight_auto_activation(service):
    service.set_policy("human", "automatic", trusted_evaluators=["evaluator"])
    v = propose(service, verified=True)
    service.review("human", v["id"], v["hash"], "defer")
    assert evaluate(service)["state"] == "pending_review"


def test_completed_workflow_rejects_new_members(service):
    run = service.start("manager", "case", "Finish")
    service.finish("manager", run["id"], "pass", "pass")
    with pytest.raises(ValueError, match="completed workflow"):
        service.start("worker", "case", "Late", workflow_id=run["workflow_id"])


def test_single_agent_can_use_human_rubric_then_approval(service):
    v = propose(service)
    event = service.snapshot()["event"][0]
    reviewed = service.human_assessment(
        v["id"],
        Assessment(
            support=3,
            applicability=3,
            completeness=3,
            contradictions=4,
            verdict="pass",
            rationale="Reviewed observable evidence",
            evaluator_version="human-rubric-v1",
            evidence=[event["id"]],
        ),
    )
    assert reviewed["evaluation"]["trusted"]
    assert reviewed["state"] == "pending_review"
    service.review("human", v["id"], v["hash"], "approve")
    assert service.discover("worker", "repair")
    assert service.claim("evaluator", "evaluate")["job"] is None


def test_merge_keeps_source_provenance_and_retires_active_source(service):
    a = propose(service, title="Status inspection")
    a = evaluate(service)
    service.review("human", a["id"], a["hash"], "approve")
    b = propose(service, title="Header inspection")
    b = evaluate(service)
    service.review("human", b["id"], b["hash"], "approve")
    run = service.start("worker", "repair", "Observe combined process")
    e = service.event(
        "worker", run["id"], Event(event_id="both", action="Check status and headers")
    )
    service.finish("worker", run["id"], "pass")
    j = service.claim("learner")
    merged = Proposal(
        **{
            **a["data"],
            "decision": "merge",
            "skill_id": a["skill_id"],
            "merged_from": [b["id"]],
            "steps": [{"instruction": "Check status and headers", "evidence": [e["id"]]}],
        }
    )
    v = service.propose("learner", j["id"], j["token"], merged)
    v = evaluate(service)
    service.review("human", v["id"], v["hash"], "approve")
    active = service.discover("worker", "repair")
    assert [x["id"] for x in active] == [v["id"]]
    assert active[0]["data"]["merged_from"] == [b["id"]]
    assert next(x for x in service.snapshot()["version"] if x["id"] == b["id"])["state"] == "merged"


def test_simultaneous_claims_cannot_lease_one_job_twice(service):
    from concurrent.futures import ThreadPoolExecutor

    run = service.start("worker", "case", "Observe")
    service.finish("worker", run["id"], "unknown")
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(service.claim, ["learner-a", "learner-b"]))
    assert sum("token" in result for result in results) == 1
