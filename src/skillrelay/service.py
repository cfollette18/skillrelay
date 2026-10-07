"""Domain rules shared by MCP, the dashboard, and instrumentation.

All policy-sensitive decisions run inside the same SQLite transaction as the write.
Trace contents are untrusted data, including instructions embedded in tool output.
"""

import difflib
import hashlib
import json
import time
import uuid
from pathlib import Path

from .models import Assessment, Event, Proposal
from .safety import clean, flags
from .store import Store, encoded

PATTERNS = {"single", "sequential", "parallel", "group_chat", "handoff", "manager_worker", "graph"}
OUTCOMES = {"pass", "fail", "unknown"}
DEFAULT_POLICY = {
    "mode": "human",
    "threshold": 90,
    "auto_distill": True,
    "lease_seconds": 120,
    "max_attempts": 3,
    "max_jobs_per_run": 6,
    "max_events_per_run": 500,
    "trusted_evaluators": [],
    "revision": 1,
}


def identity():
    return uuid.uuid4().hex


def digest(value):
    return hashlib.sha256(encoded(value).encode()).hexdigest()


class Service:
    def __init__(self, path: Path):
        self.store = Store(path)
        with self.store.connect() as db:
            if not self.store.all(db, "policy"):
                self.store.put(db, "policy", "workspace", DEFAULT_POLICY)

    def audit(self, db, actor, action, body):
        db.execute(
            "INSERT INTO audit(at,actor,action,body) VALUES(?,?,?,?)",
            (time.time(), actor, action, encoded(clean(body))),
        )

    def policy(self):
        with self.store.connect() as db:
            return self.store.get(db, "policy", "workspace")

    def set_policy(self, actor, mode, threshold=90, trusted_evaluators=None):
        if mode not in {"human", "automatic"} or not 80 <= threshold <= 100:
            raise ValueError("Mode must be human/automatic; threshold must be 80–100")
        with self.store.connect() as db:
            p = self.store.get(db, "policy", "workspace")
            p.update(mode=mode, threshold=threshold, revision=p["revision"] + 1)
            if trusted_evaluators is not None:
                p["trusted_evaluators"] = trusted_evaluators
            self.store.put(db, "policy", "workspace", p)
            self.audit(db, actor, "policy_changed", p)
            return p

    def start(
        self, actor, task, goal, pattern="single", workflow_id=None, parent=None, role="worker"
    ):
        if (
            pattern not in PATTERNS
            or not task.strip()
            or len(task) > 200
            or not goal.strip()
            or len(goal) > 4000
            or len(role) > 100
        ):
            raise ValueError("A task, bounded goal and supported pattern are required")
        with self.store.connect() as db:
            if workflow_id:
                self.store.get(db, "workflow", workflow_id)
            else:
                workflow_id = identity()
                self.store.put(
                    db,
                    "workflow",
                    workflow_id,
                    dict(
                        id=workflow_id,
                        task=task,
                        pattern=pattern,
                        owner=actor,
                        outcome="unknown",
                        status="running",
                        created=time.time(),
                    ),
                )
            if parent:
                p = self.store.get(db, "run", parent)
                if p["workflow_id"] != workflow_id:
                    raise ValueError("Parent must belong to the same workflow")
            run = dict(
                id=identity(),
                task=task,
                goal=clean(goal),
                agent=actor,
                role=role,
                workflow_id=workflow_id,
                parent=parent,
                status="running",
                outcome="unknown",
                outcome_source="self_report",
                revision=0,
                created=time.time(),
            )
            self.store.put(db, "run", run["id"], run)
            return run

    def _own(self, db, run_id, actor):
        run = self.store.get(db, "run", run_id)
        if run["agent"] != actor:
            raise PermissionError("Only the run's authenticated agent may report its events")
        return run

    def event(self, actor, run_id, event: Event):
        with self.store.connect() as db:
            run = self._own(db, run_id, actor)
            key = f"{run_id}:{event.event_id}"
            body = dict(
                id=key, run_id=run_id, workflow_id=run["workflow_id"], **clean(event.model_dump())
            )
            existing = [e for e in self.store.all(db, "event") if e["id"] == key]
            if existing:
                if existing[0] != body:
                    raise ValueError("Event ID reused with different content")
                return existing[0]
            events = self.store.all(db, "event")
            p = self.store.get(db, "policy", "workspace")
            if sum(e["run_id"] == run_id for e in events) >= p["max_events_per_run"]:
                raise ValueError("Run event budget exhausted")
            ids = {e["id"] for e in events if e["workflow_id"] == run["workflow_id"]}
            if not set(event.causes) <= ids:
                raise ValueError("Causal edges must reference existing events in this workflow")
            if event.kind == "skill_use":
                v = self.store.get(db, "version", event.skill_version)
                if v["state"] != "active":
                    raise ValueError("Applied skill version must be active")
            self.store.put(db, "event", key, body)
            run["revision"] += 1
            self.store.put(db, "run", run_id, run)
            self._invalidate(db, run_id)
            if event.kind == "skill_use" and event.success is False:
                v["freshness"] = "needs_requalification"
                self.store.put(db, "version", v["id"], v)
            if run["status"] != "running" or run["revision"] % 8 == 0:
                self._enqueue(db, run)
            return body

    def finish(self, actor, run_id, outcome, workflow_outcome=None):
        if outcome not in OUTCOMES or (workflow_outcome and workflow_outcome not in OUTCOMES):
            raise ValueError("Outcome must be pass, fail, or unknown")
        with self.store.connect() as db:
            run = self._own(db, run_id, actor)
            if workflow_outcome:
                workflow = self.store.get(db, "workflow", run["workflow_id"])
                if workflow["owner"] != actor:
                    raise PermissionError("Only the workflow owner may finish the workflow")
                workflow.update(status="completed", outcome=workflow_outcome)
                self.store.put(db, "workflow", workflow["id"], workflow)
            if run["status"] != "completed" or run["outcome"] != outcome:
                run.update(
                    status="completed",
                    outcome=outcome,
                    revision=run["revision"] + 1,
                    outcome_source="self_report",
                )
            self.store.put(db, "run", run_id, run)
            self._invalidate(db, run_id)
            return {"run": run, "job": self._enqueue(db, run)}

    def verify_outcome(self, reviewer, run_id, outcome):
        if outcome not in OUTCOMES:
            raise ValueError("Invalid outcome")
        with self.store.connect() as db:
            run = self.store.get(db, "run", run_id)
            run.update(outcome=outcome, outcome_source="human", revision=run["revision"] + 1)
            self.store.put(db, "run", run_id, run)
            self._invalidate(db, run_id)
            self.audit(db, reviewer, "outcome_verified", run)
            return self._enqueue(db, run)

    def _invalidate(self, db, run_id):
        """Late/corrected evidence withdraws prior qualifications, never mutates content."""
        run = self.store.get(db, "run", run_id)
        for v in self.store.all(db, "version"):
            job = self.store.get(db, "job", v["job_id"])
            if any(
                r["id"] == run_id and r["revision"] != run["revision"]
                for r in job["evidence"]["runs"]
            ):
                v["freshness"] = "needs_requalification"
                self.store.put(db, "version", v["id"], v)

    def _enqueue(self, db, run):
        p = self.store.get(db, "policy", "workspace")
        if not p["auto_distill"]:
            return None
        all_runs = self.store.all(db, "run")
        runs = [r for r in all_runs if r["workflow_id"] == run["workflow_id"]]
        related = [
            r
            for r in all_runs
            if r["task"] == run["task"]
            and r["workflow_id"] != run["workflow_id"]
            and r["status"] == "completed"
        ][-5:]
        runs += related
        run_ids = {r["id"] for r in runs}
        events = [e for e in self.store.all(db, "event") if e["run_id"] in run_ids]
        # Fixed evidence snapshots prevent a learner from silently changing its citations.
        evidence = {
            "runs": runs,
            "events": events,
            "workflow": self.store.get(db, "workflow", run["workflow_id"]),
        }
        key = digest({"run": run["id"], "evidence": evidence})
        jobs = self.store.all(db, "job")
        match = next((j for j in jobs if j.get("dedup") == key), None)
        if match:
            return match["id"]
        if sum(j["run_id"] == run["id"] and j["kind"] == "distill" for j in jobs) >= (
            p["max_jobs_per_run"] - (2 if run["status"] == "running" else 0)
        ):
            self.audit(db, "system", "learning_budget_exhausted", {"run": run["id"]})
            return None
        job = dict(
            id=identity(),
            kind="distill",
            run_id=run["id"],
            task=run["task"],
            evidence=evidence,
            dedup=key,
            status="queued",
            attempts=0,
            created=time.time(),
            lease_until=0,
            token=None,
        )
        self.store.put(db, "job", job["id"], job)
        return job["id"]

    def claim(self, actor, kind="distill"):
        if kind not in {"distill", "evaluate"}:
            raise ValueError("Unknown job kind")
        with self.store.connect() as db:
            p = self.store.get(db, "policy", "workspace")
            for job in self.store.all(db, "job"):
                if job["kind"] != kind or job["status"] not in {"queued", "running"}:
                    continue
                if job["status"] == "running" and job["lease_until"] > time.time():
                    continue
                if kind == "evaluate":
                    v = self.store.get(db, "version", job["version_id"])
                    if v["proposer"] == actor:
                        continue
                if job["attempts"] >= p["max_attempts"]:
                    job["status"] = "failed"
                    self.store.put(db, "job", job["id"], job)
                    continue
                job.update(
                    status="running",
                    worker=actor,
                    token=identity(),
                    lease_until=time.time() + p["lease_seconds"],
                    attempts=job["attempts"] + 1,
                )
                self.store.put(db, "job", job["id"], job)
                return {
                    **job,
                    "library": [
                        v for v in self.store.all(db, "version") if v["task"] == job["task"]
                    ][-20:],
                }
            return {"status": "waiting_for_learning_agent", "job": None}

    def _leased(self, db, actor, job_id, token):
        j = self.store.get(db, "job", job_id)
        if (
            j["status"] != "running"
            or j["worker"] != actor
            or j["token"] != token
            or j["lease_until"] <= time.time()
        ):
            raise ValueError("Expired, stale, or foreign learning lease")
        return j

    def finish_job(self, actor, job_id, token, decision, reason):
        if decision not in {"no_change", "investigate", "error"}:
            raise ValueError("Expected no_change, investigate or error")
        with self.store.connect() as db:
            j = self._leased(db, actor, job_id, token)
            j.update(
                status="queued" if decision == "error" else "completed",
                decision=decision,
                reason=clean(reason),
                token=None,
            )
            self.store.put(db, "job", j["id"], j)
            return {"status": j["status"]}

    def propose(self, actor, job_id, token, proposal: Proposal):
        with self.store.connect() as db:
            j = self._leased(db, actor, job_id, token)
            if j["kind"] != "distill":
                raise ValueError("Not a distillation job")
            data = clean(proposal.model_dump())
            evidence_ids = {e["id"] for e in j["evidence"]["events"]}
            citations = {e for step in data["steps"] for e in step["evidence"]}
            checks = {
                "references": citations <= evidence_ids,
                "instruction_screen": not flags(encoded(data)),
                "complete_run": all(r["status"] == "completed" for r in j["evidence"]["runs"]),
            }
            sid = proposal.skill_id or identity()
            versions = self.store.all(db, "version")
            peers = [v for v in versions if v["skill_id"] == sid]
            if proposal.decision != "create" and not peers:
                raise ValueError("Revisions and merges require an existing skill_id")
            if peers and proposal.decision == "create":
                raise ValueError("Existing skill requires revise or merge")
            if peers and peers[0]["task"] != j["task"]:
                raise ValueError("Cannot revise another use case")
            duplicate = next(
                (v for v in versions if v["task"] == j["task"] and v["data"] == data), None
            )
            if duplicate:
                j.update(status="completed", decision="no_change", version_id=duplicate["id"])
                self.store.put(db, "job", j["id"], j)
                return duplicate
            checks["no_conflict"] = not any(
                v["skill_id"] != sid
                and v["task"] == j["task"]
                and v["state"] == "active"
                and v["data"]["title"].casefold() == data["title"].casefold()
                and set(v["data"]["applicability"]) & set(data["applicability"])
                for v in versions
            )
            number = len(peers) + 1
            version = dict(
                id=f"{sid}@{number}",
                skill_id=sid,
                number=number,
                task=j["task"],
                data=data,
                hash=digest(data),
                proposer=actor,
                job_id=j["id"],
                checks=checks,
                confidence=0,
                state="pending_review",
                evaluation=None,
                validation="unvalidated",
                created=time.time(),
                freshness="current",
            )
            self.store.put(db, "version", version["id"], version)
            j.update(status="completed", version_id=version["id"], token=None)
            self.store.put(db, "job", j["id"], j)
            ej = dict(
                id=identity(),
                kind="evaluate",
                run_id=j["run_id"],
                task=j["task"],
                evidence=j["evidence"],
                version_id=version["id"],
                proposal=version,
                status="queued",
                attempts=0,
                created=time.time(),
                lease_until=0,
                token=None,
            )
            self.store.put(db, "job", ej["id"], ej)
            self.audit(
                db, actor, "skill_proposed", {"version": version["id"], "hash": version["hash"]}
            )
            return version

    def evaluate(self, actor, job_id, token, assessment: Assessment):
        with self.store.connect() as db:
            j = self._leased(db, actor, job_id, token)
            if j["kind"] != "evaluate":
                raise ValueError("Not an evaluation job")
            v = self.store.get(db, "version", j["version_id"])
            refs = {e["id"] for e in j["evidence"]["events"]}
            if not set(assessment.evidence) <= refs:
                raise ValueError("Evaluator cited evidence outside this job")
            p = self.store.get(db, "policy", "workspace")
            trusted = actor in p["trusted_evaluators"]
            # A self-reported successful run contributes zero provenance points.
            provenance = (
                4
                if all(
                    r["outcome_source"] != "self_report" and r["outcome"] != "unknown"
                    for r in j["evidence"]["runs"]
                )
                else 0
            )
            confidence = 5 * (
                assessment.support
                + assessment.applicability
                + assessment.completeness
                + assessment.contradictions
                + provenance
            )
            v.update(
                evaluation={**clean(assessment.model_dump()), "actor": actor, "trusted": trusted},
                confidence=confidence,
            )
            if assessment.verdict == "pass" and all(v["checks"].values()):
                v["validation"] = "evidence_supported"
            if (
                p["mode"] == "automatic"
                and trusted
                and confidence >= p["threshold"]
                and self._eligible(db, v)
            ):
                self._activate(db, v, "system", "automatic")
            self.store.put(db, "version", v["id"], v)
            j.update(status="completed", token=None)
            self.store.put(db, "job", j["id"], j)
            self.audit(db, actor, "evaluated", {"version": v["id"], "confidence": confidence})
            return v

    def _eligible(self, db, v):
        evaluation = v["evaluation"]
        job = self.store.get(db, "job", v["job_id"])
        current = all(
            self.store.get(db, "run", r["id"])["revision"] == r["revision"]
            for r in job["evidence"]["runs"]
        )
        return (
            current
            and v["state"] not in {"revoked", "rejected", "changes_requested"}
            and v["freshness"] == "current"
            and all(v["checks"].values())
            and not any(
                other["skill_id"] != v["skill_id"]
                and other["task"] == v["task"]
                and other["state"] == "active"
                and other["data"]["title"].casefold() == v["data"]["title"].casefold()
                and set(other["data"]["applicability"]) & set(v["data"]["applicability"])
                for other in self.store.all(db, "version")
            )
            and evaluation is not None
            and evaluation["verdict"] == "pass"
        )

    def _activate(self, db, v, actor, reason):
        if not self._eligible(db, v):
            raise ValueError("Required checks, evaluation, or compatibility prevent activation")
        for other in self.store.all(db, "version"):
            if other["skill_id"] == v["skill_id"] and other["state"] == "active":
                other["state"] = "superseded"
                self.store.put(db, "version", other["id"], other)
        v["state"] = "active"
        self.audit(
            db,
            actor,
            reason,
            {
                "version": v["id"],
                "hash": v["hash"],
                "policy": self.store.get(db, "policy", "workspace")["revision"],
            },
        )

    def review(self, actor, version_id, expected_hash, action, reason=""):
        if action not in {"approve", "reject", "request_changes", "defer", "rollback", "revoke"}:
            raise ValueError("Unknown review action")
        with self.store.connect() as db:
            v = self.store.get(db, "version", version_id)
            if v["hash"] != expected_hash:
                raise ValueError("Review must reference the exact content hash")
            if action in {"approve", "rollback"}:
                self._activate(db, v, actor, action)
            else:
                v["state"] = {
                    "reject": "rejected",
                    "request_changes": "changes_requested",
                    "defer": "pending_review",
                    "revoke": "revoked",
                }[action]
            self.store.put(db, "version", version_id, v)
            self.audit(
                db,
                actor,
                "review",
                {"version": version_id, "hash": expected_hash, "action": action, "reason": reason},
            )
            return v

    def dependency(self, actor, name, version, confirmed=True):
        with self.store.connect() as db:
            affected = []
            for v in self.store.all(db, "version"):
                old = v["data"]["dependencies"].get(name)
                if old is not None and old != version:
                    v["freshness"] = "incompatible" if confirmed else "needs_requalification"
                    self.store.put(db, "version", v["id"], v)
                    affected.append(v["id"])
            self.audit(
                db,
                actor,
                "dependency_changed",
                {"name": name, "version": version, "affected": affected},
            )
            return affected

    def discover(self, actor, task, query=""):
        with self.store.connect() as db:
            versions = [
                v
                for v in self.store.all(db, "version")
                if v["task"] == task
                and v["state"] == "active"
                and v["freshness"] == "current"
                and (
                    not query
                    or any(word in encoded(v["data"]).lower() for word in query.lower().split())
                )
            ]
            self.audit(
                db,
                actor,
                "discovery",
                {"task": task, "query": query, "versions": [v["id"] for v in versions]},
            )
            return versions

    def get_skill(self, actor, version_id):
        with self.store.connect() as db:
            v = self.store.get(db, "version", version_id)
            if v["state"] != "active" or v["freshness"] != "current":
                raise ValueError("Version is not available to agents")
            self.audit(db, actor, "retrieved", {"version": version_id})
            return v

    def snapshot(self, reviewer=False):
        with self.store.connect() as db:
            result = {
                kind: self.store.all(db, kind)
                for kind in ["run", "workflow", "event", "version", "job"]
            }
            # Lease tokens belong only in authenticated claim responses.
            for job in result["job"]:
                job.pop("token", None)
            result["policy"] = self.store.get(db, "policy", "workspace")
            if reviewer:
                result["audit"] = [
                    dict(seq=r[0], at=r[1], actor=r[2], action=r[3], body=json.loads(r[4]))
                    for r in db.execute("SELECT * FROM audit ORDER BY seq DESC LIMIT 200")
                ]
            return result

    def diff(self, left, right):
        with self.store.connect() as db:
            a = self.store.get(db, "version", left)
            b = self.store.get(db, "version", right)
            return "\n".join(
                difflib.unified_diff(
                    json.dumps(a["data"], indent=2, sort_keys=True).splitlines(),
                    json.dumps(b["data"], indent=2, sort_keys=True).splitlines(),
                    left,
                    right,
                )
            )
