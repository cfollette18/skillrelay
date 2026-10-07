# MCP and instrumentation API

Use stdio or authenticated Streamable HTTP at `/mcp`. `learning_status` exposes policy and queue status; `claim_learning_job` supplies evidence and the existing skill library. Only claims expose lease tokens.

| Tool | Purpose |
| --- | --- |
| `start_run` | Task namespace, goal, pattern, optional workflow and parent run, role |
| `report_event` | Idempotent event with action, result, tool, success, causal event IDs, recipient, exact skill version |
| `finish_run` | Separate run outcome and optional owner-reported workflow outcome |
| `report_outcome_check` | Independently trusted evaluator check with provenance, cited events, checker version |
| `claim_learning_job` | Lease one `distill` or `evaluate` job |
| `renew_learning_lease` | Renew a live owned lease within its attempt budget |
| `propose_skill` / `propose_skill_json` | Strict typed or JSON-string proposal submission |
| `evaluate_skill` / `evaluate_skill_json` | Strict typed or JSON-string assessment submission |
| `finish_learning_job` | No-change, investigation, or bounded error retry |
| `discover_skills` | Exact task namespace with optional keyword filtering; only active/current versions |
| `get_skill` | Exact active version plus portable Markdown |
| `learning_status` | Persisted policy and job counters |

Skill resource URI: `skill://<skill-id>/<version-number>`. Retrieval requires the version to be active and current. Historical versions are available only through reviewer inspection, not normal discovery.

Event kinds: `step`, `failure`, `verification`, `handoff`, `message`, `selection`, `join`, `termination`, `skill_use`. Causal IDs must refer to earlier events in the same workflow, which prevents cycles. A handoff recipient is descriptive; it does not cause SkillRelay to schedule an agent. Group-chat selection and termination are explicit events. Parent runs, roles, and causal links represent graph branches and joins.

## Instrumentation example

```python
import os
from pathlib import Path
from skillrelay.instrumentation import Recorder

recorder = Recorder("http://127.0.0.1:8765", os.environ["SKILLRELAY_AGENT_TOKEN"],
                    spool=Path(".trace-spool"))
run = recorder.start("invoice-import", "Import invoices", pattern="single")
recorder.event(run["id"], "Validate column names", "Expected schema found",
               tool="csv-import", kind="verification", success=True)
recorder.finish(run["id"], "pass", workflow_outcome="pass")
recorder.close()
```

The client spool is written before event delivery and replayed with the same event IDs. `start` and `finish` errors are visible to the caller; no silent success is reported.

## Reviewer API

The console uses a separate bearer credential and `/api/snapshot`, `/api/review`, `/api/assess`, `/api/policy`, `/api/outcome`, `/api/dependency`, and `/api/diff`. Mutations require POST. Review payloads contain `version_id`, `expected_hash`, `action`, and optional `reason`. Dependency payloads contain `name`, `version`, and `confirmed`.

Reviewer APIs are intentionally absent from the MCP tool catalog. Programmatic access does not mean the learning agent should receive reviewer credentials. The local CLI is an operator interface.
