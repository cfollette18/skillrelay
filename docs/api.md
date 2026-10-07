# MCP tools and local operator commands

The server supports stdio and authenticated Streamable HTTP at `/mcp`. No other HTTP routes are exposed.

| MCP tool | Purpose |
| --- | --- |
| `start_run` | Task namespace, goal, pattern, optional workflow and parent run, role |
| `report_event` | Idempotent observable action/result, tool, success, causal IDs, recipient, exact skill version |
| `finish_run` | Separate run outcome and optional owner-reported workflow outcome |
| `list_runs` | Filter recent runs by task and pass/fail/unknown outcome |
| `get_run_trace` | Read a run, its workflow context, and observable events |
| `report_outcome_check` | Independently trusted evaluator check with cited events and checker version |
| `claim_learning_job` | Lease one `distill` or `evaluate` job, with evidence and existing skill library |
| `renew_learning_lease` | Renew a live owned lease within its attempt budget |
| `propose_skill` / `propose_skill_json` | Strict typed or JSON-string proposal submission |
| `evaluate_skill` / `evaluate_skill_json` | Strict typed or JSON-string assessment submission |
| `finish_learning_job` | No-change, investigation, or bounded error retry |
| `discover_skills` | Exact task namespace with optional keyword filtering; active/current versions only |
| `get_skill` | Retrieve an exact active version and portable Markdown |
| `learning_status` | Persisted policy and queue status without lease tokens |

Skill resource: `skill://<skill-id>/<version-number>`. Historical content is available to operators through `inspect`, not through normal agent distribution.

Event kinds: `step`, `failure`, `verification`, `handoff`, `message`, `selection`, `join`, `termination`, `skill_use`. Causal IDs must reference earlier events in the same workflow. Handoff and selection events describe external orchestration; they do not schedule agents.

## Framework instrumentation

`Recorder` uses the official MCP client under the hood. Its event spool survives transient delivery failures and replays stable event IDs.

```python
import os
from pathlib import Path
from skillrelay.instrumentation import Recorder

recorder = Recorder("http://127.0.0.1:8765/mcp", os.environ["SKILLRELAY_AGENT_TOKEN"],
                    spool=Path(".trace-spool"))
try:
    run = recorder.start("invoice-import", "Import invoices", pattern="single")
    recorder.event(run["id"], "Validate columns", "Expected schema found",
                   tool="csv-import", kind="verification", success=True)
    recorder.finish(run["id"], "pass", workflow_outcome="pass")
finally:
    recorder.close()
```

No direct REST ingestion endpoint exists. Completion does not imply success; choose `unknown` when the outcome is not verified.

## Operator CLI

All commands accept `--home /path/to/workspace` before the subcommand.

| Command | Purpose |
| --- | --- |
| `install-skill DESTINATION` | Copy bundled workflow skill into a new client skill directory; no workspace initialization or overwrites |
| `init`, `credential agent`, `add-agent NAME` | Initialize/provision agent access |
| `status`, `traces [--run ID]`, `export`, `audit` | Inspect local evidence and decisions |
| `skills [--task TASK]`, `inspect VERSION` | Inspect version history and exact hashes |
| `assess VERSION --file assessment.json` | Record a human assessment |
| `review VERSION HASH ACTION [--reason TEXT]` | Approve/request_changes/reject/defer/revoke/rollback |
| `outcome RUN pass\|fail\|unknown` | Human verification of a run outcome |
| `dependency NAME VERSION [--uncertain]` | Trigger compatibility requalification |
| `diff LEFT RIGHT` | Compare immutable version content |
| `policy --mode human\|automatic ...` | Persist activation policy |
| `work --command-json '[...]' --kind distill\|evaluate` | Drive a configured external learning agent |

Example human assessment (`assessment.json`):

```json
{
  "support": 3,
  "applicability": 3,
  "completeness": 3,
  "contradictions": 4,
  "verdict": "pass",
  "rationale": "Each instruction is supported by the cited observable results.",
  "evidence": ["<run-id>:<event-id>"],
  "evaluator_version": "human-rubric-v1"
}
```

Replace the example citation with actual event IDs. Rubric levels range from 0 (absent) to 4 (complete); `contradictions` measures freedom from contradictions. Assessments do not bypass required checks or mandatory human activation. CLI access is an operator/filesystem trust boundary; agents never receive approval tools over MCP.
