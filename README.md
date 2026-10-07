# SkillRelay

**An MCP server that turns agent experience into reusable, evaluated skills.**

Connect your existing agent and model. SkillRelay captures observable workflows, queues learning jobs, checks evidence, and distributes approved skills through MCP tools and portable `SKILL.md` resources.

SkillRelay is strictly an MCP server. It has no web app, dashboard, or REST API. Use stdio or authenticated Streamable HTTP at `/mcp`; local operator commands handle human review and administration.

## Quick start

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/cfollette18/skillrelay.git
cd skillrelay
uv sync --locked
uv run skillrelay init
```

Add to your MCP client, replacing the repository path:

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

Or start the authenticated HTTP transport:

```bash
uv run skillrelay serve --transport http
uv run skillrelay credential agent
```

Connect your client to `http://127.0.0.1:8765/mcp` with `Authorization: Bearer <agent token>`. This is a protocol endpoint, not a browser page. Provision separate identities with `skillrelay add-agent evaluator`; restart the HTTP server after adding credentials.

## Bundled workflow skill

Install [skillrelay-workflow](src/skillrelay/bundled/skillrelay-workflow/SKILL.md) into a new directory in your agent client's skills location:

```bash
uv run skillrelay install-skill /path/to/client/skills/skillrelay-workflow
```

The destination is the skill folder itself. The command copies the instructions and learning reference bundled with the Python package; it also works with a wheel installation using `skillrelay install-skill ...`. Existing destinations are refused to preserve local edits. To update, install to a new directory and compare before replacing your installed copy. It does not create a SkillRelay workspace, configure your client, or change approval policy.

Enable or reload skills as required by your client, and keep the MCP connection configured above. In clients supporting named skill invocation, request: “Use $skillrelay-workflow for this task.” Other clients can load the installed `SKILL.md` as task guidance. No client-specific metadata disables implicit selection.

The skill guides discovery before substantive work, observable trace capture, exact-version use reporting, and a bounded distillation step afterward. A separate learning reference covers independent evaluation and the human-review boundary. Use the same configured task namespace across sessions so skills remain discoverable. If a runtime adapter already captures events, follow its run-ownership contract to avoid duplicate reporting.

**Participation remains best effort:** an MCP connection or installed skill cannot force model tool calls. Learning jobs still need a connected learner/evaluator or the configured external driver. Runtime adapters are needed to enforce lifecycle calls. This bundled workflow guide is maintained with SkillRelay; learned use-case skills continue to be retrieved dynamically through MCP.

## The learning loop

1. **Observe:** report actions, tool results, errors, checks, and causal links. Run and workflow outcomes remain separate.
2. **Queue:** completed runs and checkpoints automatically create durable jobs with fixed evidence snapshots and recent related runs.
3. **Distill:** your connected agent inspects the evidence and existing library, then creates, revises, merges, investigates, or decides no change. Every proposed step cites source events.
4. **Evaluate:** a separate agent—or the human operator—assesses support, applicability, completeness, and contradictions. SkillRelay computes the score and enforces required checks.
5. **Activate:** human review is the default. Optional automatic activation needs a trusted evaluator, passing checks, and a high confidence score. Otherwise the skill waits for review.
6. **Reuse:** agents retrieve exact compatible versions and record actual use separately from discovery. Failures, changed dependencies, or corrected evidence trigger requalification.

Auto-distillation is enabled, but a connected learning agent must process the jobs. SkillRelay does not configure a model, observe unreported actions, or orchestrate your agents.

## Human review from your terminal

```bash
uv run skillrelay skills
uv run skillrelay inspect '<skill-id>@1'
uv run skillrelay review '<skill-id>@1' '<content-hash>' approve --reason 'Evidence checked'
uv run skillrelay audit
```

Approval requires a passing assessment and all required checks. For a single connected agent, provide the human assessment yourself:

```bash
uv run skillrelay assess '<skill-id>@1' --file assessment.json
```

See the [assessment schema and operator commands](docs/api.md). `review` also supports `request_changes`, `reject`, `defer`, `revoke`, and eligible-version `rollback`. Revisions are immutable and need their own evaluation and approval.

```bash
uv run skillrelay diff '<skill-id>@1' '<skill-id>@2'
uv run skillrelay review '<skill-id>@1' '<content-hash>' rollback
```

Agent-facing MCP tools never expose approval or policy mutation. Local operator commands assume a trusted OS user; keep the workspace filesystem out of untrusted agents' reach when that boundary matters.

## Automatic activation with human fallback

```bash
uv run skillrelay policy --mode automatic --threshold 90 --trust-evaluator evaluator
# Restore mandatory human approval, including for in-flight proposals:
uv run skillrelay policy --mode human
```

The evidence rubric awards up to 20 points each for support, applicability, completeness, absence of contradictions, and outcome provenance. Self-reported outcomes receive zero provenance points. Low confidence, unknown results, evaluation failures, or missing evaluator trust cannot automatically activate a skill. No score overrides a failed hard check.

Confidence is a rubric score, not a probability or a measured performance improvement. Behavioral benchmarking remains deferred; passing evidence checks earn the label `evidence_supported`.

## Out-of-the-box observability

Use MCP `list_runs`, `get_run_trace`, and `learning_status` to inspect evidence and learning. Operators can use:

```bash
uv run skillrelay status
uv run skillrelay traces
uv run skillrelay traces --run '<run-id>'
uv run skillrelay export > evidence.json
```

SQLite stores trace graphs, immutable proposals, evaluations, job leases, and the audit trail. A framework-independent recorder and optional Hermes hook send events through MCP. There is an optional OpenTelemetry exporter interface; no external observability platform or Langfuse integration is required.

Supported external workflow patterns: single-agent, sequential, parallel, group chat, handoff, manager–worker, and graph workflows. SkillRelay records roles, parents, handoffs, messages, selections, joins, and termination; your agent framework executes them.

## Continuous learning

Your agent can claim jobs after each task. Alternatively, run a bounded external command driver against an agent already configured for SkillRelay:

```bash
uv run skillrelay work --kind distill --max-invocations 20 \
  --command-json '["hermes", "chat", "--max-turns", "16", "-q", "{prompt}"]'
```

Use a separate identity for `--kind evaluate`. The driver bounds invocation count and wall time; leases and retries are also bounded. Model-token and dollar budgets belong to your agent runtime.

## Demo

[Play/download the terminal MCP demo](https://github.com/cfollette18/skillrelay/releases/download/v0.2.0/skillrelay-mcp-demo.mp4) · [Real Hermes evidence](docs/media/demo-evidence.json) · [Reproduction steps](docs/hermes.md)

The demo uses a synthetic invoice fixture and real Hermes sessions. Terminal output shows MCP discovery, observable failure/success evidence, CLI approval, and exact-version reuse. It is a functional demonstration, not a behavioral benchmark.

## Development and deployment

```bash
uv run ruff check src tests examples integrations
uv run ruff format --check src tests examples integrations
uv run pytest -q
uv build

docker build -t skillrelay .
docker run --rm -p 127.0.0.1:8765:8765 -v skillrelay-data:/data skillrelay
```

One trusted workspace per deployment. See [architecture and boundaries](docs/architecture.md) and [MCP/CLI reference](docs/api.md). This release removes the earlier browser prototype; old workspace databases and agent credentials remain usable.

Inspired by the MCP distribution layer and self-distilling skill loop in [the source video](https://www.youtube.com/watch?v=u-o0sW9nwmk).
