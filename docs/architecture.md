# Architecture and boundaries

SkillRelay separates experience capture, generation, evaluation, and publication. The connected agent owns model selection and orchestration. The server owns durable state and eligibility.

```text
External agent(s) ── MCP / recorder ──► runs + causal events
                                            │
                                     checkpoint / completion
                                            ▼
                                      leased learning job
                                            │
Connected learner ── cited proposal ────────► immutable version
                                            │
Separate evaluator ── cited assessment ─────► required gates + rubric
                                            │
                                  persisted activation policy
                                     /                \
                            human decision       automatic threshold
                                     \                /
                                       active version
                                            │
                                     MCP / SKILL.md
```

## Persistence and concurrency

SQLite WAL plus `BEGIN IMMEDIATE` serializes each mutation, including activation and its policy check. Logical records use a versioned schema (`PRAGMA user_version=1`); records are JSON to keep this small deployment easy to inspect. Event IDs are unique within a run. Reusing an ID with different data fails. Evidence snapshots never change after a job is created.

Jobs have opaque lease tokens, authenticated owners, a 120-second lease, up to three attempts, and a ten-minute renewal ceiling per attempt. Expired workers cannot submit. Six distillation jobs per run and 500 events per run bound capture; two job slots are reserved for completion and late evidence. The command driver separately limits invocations and wall time. Agent runtimes enforce model-token and cost budgets.

This is a small-workspace design, not a high-volume telemetry warehouse: queries scan logical record sets and snapshots can grow. There is no retention daemon, hosted tenancy, billing, distributed scheduler, or unlimited ingestion promise. Export via `skillrelay export`; back up SQLite using its backup API or stop writers before copying database files. Store the private config alongside the backup with appropriate access controls.

## Evidence and evaluations

Captured evidence is limited to observable inputs, outputs, errors, checks, and orchestration events. Do not submit hidden reasoning. Best-effort redaction runs before persistence and in the instrumentation spool. Review what is appropriate to collect; regex redaction is not comprehensive DLP.

Related completed runs with the same task namespace are included in learning snapshots (up to five). This lets learners compare failure and success. Existing versions are included in claims to support revision instead of repeated creation. Explicit merges cite source versions, preserve their applicability and dependency constraints, and retire their active pointers only on activation. Exact duplicate content is reused; obvious same-title/same-applicability active conflicts are blocked. Semantic overlap or contradiction requires the evaluator/reviewer; there is no embedding search or automatic semantic merge engine.

Every step must cite IDs from the fixed snapshot. Required structural gates include valid references, instruction screening, and completed source runs. For a single connected agent, a human can supply the assessment in the console.
The evaluator supplies separate 0–4 rubric levels with cited reasoning about observable evidence. Server computation adds outcome-provenance points. An agent's own success declaration is recorded as `self_report`, regardless of what it writes in text. Humans can verify outcomes; configured independent evaluator identities can submit outcome checks.

Reviewer policy is read inside the activation transaction. Changing to human mode blocks automatic activation of jobs already in flight. Scores cannot override a failed hard gate. Evaluator error/unknown, low score, or lack of evaluator trust leaves the skill for review. Human approval still requires a passing evaluation and required checks.

## Versions and requalification

Each proposal has immutable skill content, a monotonically increasing version within its skill ID, and a SHA-256 content hash. Mutable lifecycle metadata stores evaluation, state, and freshness. Reviews bind to exact hashes. Revising content creates another version and requires its own evaluation and activation. Rollback activates an eligible older version and supersedes the currently active version; revoked or incompatible versions cannot be restored through rollback.

Late evidence or corrected outcomes mark affected versions as needing requalification. Confirmed dependency changes mark versions incompatible; uncertain changes also withhold discovery pending requalification. Reported failure when applying a skill withdraws it from discovery. Requalify by producing a new version against current evidence/dependencies. Activation rechecks source-run revisions and active conflicts to prevent races.

## Authorization

The HTTP interface uses separate random bearer tokens for agents and reviewers. Agents cannot access `/api/*`; reviewers cannot use their credential for MCP or ingestion. Each additional agent gets its own token mapped to a server-side identity. Evaluation cannot be performed by the same identity that proposed the skill. Only the owning agent can write a run's events; workflow completion belongs to its owner. No roles are accepted from request bodies.

Stdio and the local CLI assume a trusted OS user. A process with filesystem access to the workspace can read credentials or edit SQLite; this is not an isolation boundary against that OS user. For separate identities use HTTP tokens and isolate reviewer credentials from agents. The default bind address is loopback. There is no public-hosting/OAuth/multi-tenant claim. Cross-origin requests are rejected, and the MCP SDK enforces host validation.

## Observability integration

Built-in views cover workflows, trace events and causal IDs, learning jobs, exact skill versions, rubric scores, policy, and review/retrieval history. Retrieval and actual `skill_use` events are distinct; neither alone proves improvement.

`Recorder` provides framework-independent HTTP capture and a local event spool with idempotent replay. Hermes has an optional hook adapter. Its session-end event records `unknown`: a finished agent turn is not proof of task success. Capture failures log a warning; process crashes before a run starts cannot be recovered from the event spool.

`TraceExporter` provides an optional extension seam. `OpenTelemetryExporter` emits run identifiers/outcomes and tool-event identifiers through a caller-configured tracer; it exports neither prompts nor output bodies. These are export-time spans, not reconstructed timing measurements. No external backend or Langfuse integration is bundled.

A `BehavioralEvaluator` protocol reserves the comparative-evaluation seam. The actual benchmark runner, held-out suite, and performance claims are deferred.
