# SkillRelay

**Turn agent experience into reusable skills—with evidence, evaluation, and approval.**

SkillRelay is a local-first MCP server for agents that learn across tasks. Connect your existing agent and model, capture observable workflows, and distill successful techniques and failure lessons into versioned skills. SkillRelay distributes approved instructions back through MCP tools and portable `SKILL.md` resources.

It includes its own SQLite trace store, learning queue, evaluation gates, and browser review console. No observability account, Langfuse integration, or separate model API key is required.

> **v0.1 scope:** one trusted workspace, externally orchestrated agents, explicit instrumentation. SkillRelay cannot observe unreported tool calls or make an offline agent learn. Auto-distillation queues jobs; a connected learning agent or the optional command driver processes them. Behavioral benchmarking is intentionally deferred.

## Quick start

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/cfollette18/skillrelay.git
cd skillrelay
uv sync --locked
uv run skillrelay init
uv run skillrelay serve --transport http
```

Open **http://127.0.0.1:8765**. In a separate terminal, retrieve the local reviewer credential:

```bash
uv run skillrelay credential reviewer
```

Paste it into the console. It stays in tab memory. Human review is enabled by default and stored in the database.

Connect any MCP client using stdio (replace the repository path):

```json
{
  "mcpServers": {
    "skillrelay": {
      "command": "uv",
      "args": ["--directory", "/absolute/path/skillrelay", "run", "skillrelay", "serve"]
    }
  }
}
```

Or connect to `http://127.0.0.1:8765/mcp` with `Authorization: Bearer <agent token>` from `skillrelay credential agent`. Never give the reviewer token to the agent. See [Hermes setup and demo](docs/hermes.md).

## The learning loop

1. **Observe:** start a run; record tool actions, results, messages, handoffs, and causal edges. Mark task and workflow outcomes separately as pass, fail, or unknown.
2. **Queue:** checkpoints and completed runs automatically create durable learning jobs with fixed evidence snapshots, including recent related runs.
3. **Distill:** a connected agent claims a job, inspects existing skills, and chooses create, revise, merge, investigate, or no change. Every proposed step cites trace evidence.
4. **Evaluate:** a different agent or the human reviewer checks support, applicability, completeness, and contradictions. The server validates structure and citations and computes an evidence-confidence score.
5. **Activate:** human review is the default. Optional automatic mode requires passing checks, a trusted evaluator, and the configured confidence threshold. Otherwise the proposal waits for a human.
6. **Reuse:** agents discover compatible active skills, retrieve an exact version, and report actual application separately from retrieval. Failures or changed evidence/dependencies withdraw qualification.

Learning-agent failures retry within bounded leases and attempt budgets. No connected learner means the queue waits—it does not manufacture a skill.

## What is included

| Capability | Implementation |
| --- | --- |
| Distribution | MCP stdio and authenticated Streamable HTTP; portable skill Markdown and resource templates |
| Tracing | Runs, outcomes, events, causal references, idempotent ingestion, redaction, JSON export |
| Multi-agent support | Sequential, parallel, group chat, handoff, manager–worker, and graph workflows; orchestration stays external |
| Learning | Durable leases, bounded retries, checkpoints, immutable evidence, related-run context, external agent command driver |
| Evaluations | Structural checks, citation checks, instruction screening, completion checks, conservative conflict checks, cited semantic rubric |
| Review | Approve, request changes, reject, defer, revoke; exact content hashes, persisted policy, audit trail |
| Versions | Immutable content, diffs, eligible-version rollback, dependency invalidation, stale-evidence checks |
| Observability | Local console for traces, skills, jobs, confidence, policy, and decisions; optional OTel export interface |
| Hermes | Real MCP demo runner, synthetic failure/success task, optional tool-hook recorder |

The server does **not** execute proposed skill instructions. Its instruction screening and redaction are best effort. The semantic evaluator still needs judgment; a high rubric score is not calibrated probability or proof of behavioral improvement.

## Activation policy

There are two modes. Both always enforce required checks.

- **Human:** every activation requires a reviewer decision, regardless of confidence.
- **Automatic with fallback:** requires a trusted independent evaluator, passing assessment, current evidence/compatibility, and confidence ≥ the configured threshold (default 90/100). Anything insufficient stays pending review.

The score assigns up to 20 points each to support, applicability, completeness, lack of contradictions, and outcome provenance. Self-reported outcomes earn zero provenance points, so self-report alone caps the score at 80. Trusted evaluators are provisioned by the workspace operator; clients cannot declare themselves trusted in a payload.

```bash
# Create separate HTTP identity. Prints a private token; restart HTTP after provisioning.
uv run skillrelay add-agent evaluator

# Opt in deliberately. Human mode remains the initial default.
uv run skillrelay policy --mode automatic --threshold 90 --trust-evaluator evaluator

# Switch back; in-flight proposals will obey this mode at activation time.
uv run skillrelay policy --mode human
```

A passing evidence assessment is labeled `evidence_supported`. This release does not assign `behavior_validated` or claim benchmark gains.

## Run learning automatically

Your client can call the learning tools after each task. For continuous learning, run an external agent command with the bounded driver; the external agent must already be configured to connect to SkillRelay:

```bash
uv run skillrelay work --kind distill --max-invocations 20 \
  --command-json '["hermes", "chat", "--max-turns", "16", "-q", "{prompt}"]'
```

For a single connected agent, the reviewer can complete the rubric in the console before approving.

Run an evaluator driver with `--kind evaluate` under a **different authenticated agent identity**. The driver uses no shell interpolation and caps each invocation's wall time. Model-token and dollar budgets remain the responsibility of your agent runtime. Local stdio identities are trusted configuration; use separately provisioned HTTP tokens when identity isolation matters.

## Development

```bash
uv sync --locked
uv run ruff check src tests examples integrations
uv run ruff format --check src tests examples integrations
uv run pytest -q
uv build
```

Tests cover MCP transport, reviewer isolation, policy changes during learning, stale leases, rollback, hard gates, evidence changes, and workflow patterns. See [architecture and boundaries](docs/architecture.md), [MCP API](docs/api.md), and [demo instructions](docs/hermes.md).

## Docker

```bash
docker build -t skillrelay .
docker run --rm -p 127.0.0.1:8765:8765 -v skillrelay-data:/data skillrelay
# Retrieve the reviewer credential in another terminal, using the running container ID:
docker exec <container> skillrelay --home /data credential reviewer
```

## Inspiration

The project explores the MCP-as-distribution-layer and self-distilling skill loop discussed in [the source video](https://www.youtube.com/watch?v=u-o0sW9nwmk). SkillRelay is an independent implementation with explicit evidence, evaluation, and activation boundaries.
