# Hermes + SkillRelay MCP

Hermes supplies the agent runtime and model. SkillRelay provides tools for evidence capture, learning, evaluations, and skill distribution. There is no browser application.

Add to the chosen Hermes profile's `config.yaml`:

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

Use another profile with `--agent hermes-evaluator` for independent evaluations. Both point to the same workspace; insert `--home /path/to/workspace` before `serve` to customize it. Stdio identity assumes a trusted local process. For separately authenticated identities use Streamable HTTP at `/mcp` with provisioned agent tokens.

## Run the real demo

The synthetic fixture has a UTF-8 BOM and semicolon delimiter. The naive parser fails; the parser for the documented format succeeds. The runner invokes the actual Hermes installation and configured model in isolated private profiles under `.demo/`. Your regular profile is not modified.

```bash
uv sync --group demo
uv run --group demo python examples/hermes/run_demo.py --stage learn
uv run --group demo python examples/hermes/run_demo.py --stage evaluate
uv run skillrelay --home .demo/workspace skills
uv run skillrelay --home .demo/workspace inspect '<skill-id>@1'
uv run skillrelay --home .demo/workspace review '<skill-id>@1' '<hash>' approve
uv run --group demo python examples/hermes/run_demo.py --stage reuse
```

Inspect actual use with `skillrelay --home .demo/workspace traces`. The fresh session discovers the active skill, retrieves the exact version, executes the parser, and reports `skill_use` through MCP. Completion remains self-report unless independently checked.

For a second immutable version:

```bash
uv run --group demo python examples/hermes/run_demo.py --stage revise
uv run --group demo python examples/hermes/run_demo.py --stage evaluate
uv run skillrelay --home .demo/workspace diff '<skill-id>@1' '<skill-id>@2'
```

`--stage distill` resumes a completed run's queued learning job. `--workspace` and `--profile-root` let recordings use separate private copies. Override `--hermes` or `--base-profile` for a different installation.

Some Hermes/model combinations wrap nested arguments as XML-like objects. Use the strict JSON-string alternatives `propose_skill_json` and `evaluate_skill_json`; they enforce the same schemas and policy as typed submissions.

## Terminal recording

The terminal demo uses existing real Hermes evidence, makes actual MCP and CLI calls, and starts another real Hermes reuse session. It performs scripted operator approvals and rollback in an isolated database copy. Only idle waiting is compressed during playback; no model reasoning or credentials are published.

After creating/evaluating the two versions above, with version 1 active:

```bash
asciinema rec --cols 106 --rows 32 -i 2 \
  -c '.venv/bin/python examples/hermes/terminal_demo.py' \
  docs/media/skillrelay-mcp-demo.cast
agg --idle-time-limit 5 --font-size 18 --theme github-dark \
  docs/media/skillrelay-mcp-demo.cast /tmp/skillrelay-demo.gif
ffmpeg -i /tmp/skillrelay-demo.gif -c:v libx264 -pix_fmt yuv420p \
  -movflags +faststart docs/media/skillrelay-mcp-demo.mp4
```

[MP4 video](https://github.com/cfollette18/skillrelay/releases/download/v0.2.0/skillrelay-mcp-demo.mp4) · [Replayable terminal recording](media/skillrelay-mcp-demo.cast) · [Evidence](media/demo-evidence.json)

This is a controlled functional demo on synthetic data. It does not claim held-out behavioral improvements.

## Optional native capture and continuous learning

Copy `integrations/hermes/skillrelay/` into your chosen Hermes profile's `plugins/` directory and make the Python package importable in that environment. Configure `SKILLRELAY_URL=http://127.0.0.1:8765/mcp`, `SKILLRELAY_AGENT_TOKEN`, and optional `SKILLRELAY_TASK` privately.

The hook records observable `post_tool_call` events through the official MCP client and closes runs as `unknown`. It skips SkillRelay's own tools to avoid recursion and lease-token capture. Explicit reporting is still needed for verified outcomes and multi-agent causal links.

For automatic processing, use `skillrelay work` with a configured Hermes command. Run the evaluator under a separate identity. The driver bounds invocations and wall time; SkillRelay enforces durable leases and retry budgets. Human approval and policy changes remain local operator commands, outside the agent tool catalog.
