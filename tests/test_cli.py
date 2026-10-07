import json
import subprocess
import sys

from skillrelay.models import Event, Proposal
from skillrelay.service import Service


def test_operator_can_review_without_network_api(tmp_path):
    service = Service(tmp_path / "skillrelay.db")
    run = service.start("agent", "case", "Observe a result")
    event = service.event(
        "agent", run["id"], Event(event_id="a", action="Checked output", result="PASS")
    )
    service.finish("agent", run["id"], "pass")
    job = service.claim("learner")
    version = service.propose(
        "learner",
        job["id"],
        job["token"],
        Proposal(
            title="Check output",
            summary="Verify observable output",
            applicability=["this case"],
            steps=[{"instruction": "Check output", "evidence": [event["id"]]}],
            checks=["Output exists"],
        ),
    )
    assessment = tmp_path / "assessment.json"
    assessment.write_text(
        json.dumps(
            {
                "support": 3,
                "applicability": 3,
                "completeness": 3,
                "contradictions": 4,
                "verdict": "pass",
                "rationale": "Reviewed the observable result",
                "evidence": [event["id"]],
                "evaluator_version": "human-v1",
            }
        )
    )

    def cli(*args):
        result = subprocess.run(
            [sys.executable, "-m", "skillrelay.cli", "--home", str(tmp_path), *args],
            text=True,
            capture_output=True,
            check=True,
        )
        return json.loads(result.stdout)

    assert cli("inspect", version["id"])["state"] == "pending_review"
    assert cli("assess", version["id"], "--file", str(assessment))["evaluation"]["trusted"]
    assert cli("review", version["id"], version["hash"], "approve")["state"] == "active"
    assert cli("traces", "--run", run["id"])["events"][0]["id"] == event["id"]
    assert cli("status")["active_skills"] == 1
    assert cli("audit")
