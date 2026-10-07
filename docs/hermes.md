# Hermes integration and real demo

Hermes stays the agent runtime and supplies the model. SkillRelay stays the MCP learning/distribution service. The integration follows [Hermes MCP configuration](https://hermes-agent.nousresearch.com/docs/user-guide/features/mcp/).

Add to your chosen Hermes profile's `config.yaml`:

```yaml
mcp_servers:
  skillrelay:
    command: uv
    args:
      - --directory
      - /absolute/path/skillrelay
      - run
      - skillrelay
      - serve
      - --agent
      - hermes-worker
```

Use a separate profile with `--agent hermes-evaluator` for evaluation. Both profiles should point to the same SkillRelay workspace. If you customize the workspace, insert `--home /path/to/workspace` before `serve`.

For stronger identity separation, use the HTTP MCP URL and distinct provisioned agent tokens instead of local stdio identities. Never add the reviewer token to a Hermes profile.

## Reproduce the video workflow

The repository includes a synthetic UTF-8 BOM/semicolon invoice fixture, a deliberately naive parser, a correct parser for that exact format, and a runner that invokes **real Hermes**. The source agent run is live; the fixture and failure are intentionally controlled demo inputs. This is not a held-out behavioral benchmark.

```bash
uv sync --group demo
uv run --group demo playwright install chromium
uv run --group demo python examples/hermes/run_demo.py --stage learn
uv run --group demo python examples/hermes/run_demo.py --stage evaluate
uv run skillrelay --home .demo/workspace serve --transport http
uv run skillrelay --home .demo/workspace credential reviewer
```

The runner uses your existing Hermes installation and model configuration, copied into isolated private profiles under `.demo/`. Your regular profile is not changed. Model calls use the credentials already configured in Hermes. Override `--hermes` and `--base-profile` for a different installation. Private configs and logs are gitignored; never publish `.demo/`.

In the console inspect the actual failure/success events, proposal citations, checks, and separate evaluator assessment. Approve the exact skill version. Then start a fresh session:

```bash
uv run --group demo python examples/hermes/run_demo.py --stage reuse
```

Verify that `skill_use` records the exact version and observed output. Use the console's version diff and rollback controls for later revisions. `--stage distill` can resume learning if the initial run completed but its proposal submission failed.

Some Hermes/model combinations wrap nested tool arguments in XML-like objects. The `propose_skill_json` and `evaluate_skill_json` tools accept strict JSON strings for these clients; they enforce exactly the same schema and activation rules as typed submissions.

## Automatic learning driver

For ongoing work use `skillrelay work` with a configured Hermes command and profile. It asks Hermes to claim and process one job per invocation; use a different profile/identity for evaluator work. Maximum invocations, subprocess timeout, leases, and retry limits bound execution. The server does not own or select a model.

## Optional native tool capture

Copy `integrations/hermes/skillrelay/` into the chosen Hermes profile's `plugins/` directory and make the `skillrelay` Python package importable in Hermes' environment. Check dependency compatibility before installing it into an existing environment. Configure `SKILLRELAY_URL`, `SKILLRELAY_AGENT_TOKEN`, and optional `SKILLRELAY_TASK` in that profile's private environment.

The plugin records observable `post_tool_call` events and closes runs with `unknown` on session end. It skips SkillRelay's own tools to avoid recursion and lease-token capture. It does not declare success or automatically approve a skill. Use explicit reporting for task outcomes and multi-agent causal links; hooks cannot infer those reliably.

## Published recording

[Video](media/skillrelay-demo.mp4) and [redacted evidence](media/demo-evidence.json) capture
real Hermes learning, independent evaluation, and fresh-session reuse. Reviewer actions in the
browser recording are scripted demonstrations, visibly labeled. The original configured model's
nested-argument encoding initially failed; the JSON submission tools resolved it. The first
successful proposal used a retry of the original job. No unsuccessful attempt was relabeled as a
successful model call.

The second version narrows the original skill's applicability. It was independently evaluated
under automatic mode with a threshold of 90, received 60, and stayed pending review. The recording
then activates it through the reviewer interface and rolls back to version 1. Both immutable
versions and the actual applied version ID are present in the published evidence.

To create those later chapters after reuse:

```bash
uv run --group demo python examples/hermes/run_demo.py --stage revise
uv run skillrelay --home .demo/workspace policy --mode automatic --threshold 90 \
  --trust-evaluator hermes-evaluator
uv run --group demo python examples/hermes/run_demo.py --stage evaluate
uv run --group demo python examples/hermes/record_console.py --chapter versions
```

`record_console.py` uses Playwright against the already running demo server. `--chapter review`
records the first review/activation; `--chapter reuse` records the resulting trace/audit views.
Only use these scripted reviewer actions in the synthetic demo workspace. Export publishable
trace evidence with `uv run python examples/hermes/export_demo.py`.
