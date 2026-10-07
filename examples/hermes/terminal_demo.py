"""Live MCP/CLI terminal walkthrough. Uses an isolated copy of real Hermes evidence."""

import asyncio
import json
import logging
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from mcp import Client, StdioServerParameters

from skillrelay.config import initialize
from skillrelay.safety import clean
from skillrelay.service import Service

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / ".demo" / ("terminal-" + datetime.now().strftime("%Y%m%d-%H%M%S"))
HOME = OUTPUT / "workspace"
logging.basicConfig(level=logging.ERROR)


def emit(text="", color=""):
    code = {"green": "32", "cyan": "36", "yellow": "33", "dim": "90"}.get(color)
    print((f"\033[{code}m" if code else "") + str(text) + ("\033[0m" if code else ""), flush=True)


def chapter(number, title):
    print("\033[2J\033[H", end="", flush=True)
    emit("SKILLRELAY  /  MCP SERVER", "cyan")
    emit("Actual MCP calls + local operator commands | synthetic invoice fixture", "dim")
    emit("Scripted walkthrough; output fields summarized for readability.", "dim")
    emit("─" * 100, "dim")
    emit(f"{number}. {title}\n", "cyan")
    time.sleep(0.7)


def command(label):
    emit("$ " + label, "green")
    time.sleep(0.5)


def cli(*args):
    result = subprocess.run(
        [sys.executable, "-m", "skillrelay.cli", "--home", str(HOME), *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def unpack(result):
    if result.is_error:
        raise RuntimeError(str(result.content))
    body = result.structured_content
    if isinstance(body, dict) and set(body) == {"result"}:
        return body["result"]
    return body


async def main():
    initialize(HOME)
    with sqlite3.connect(ROOT / ".demo/workspace/skillrelay.db") as source:
        with sqlite3.connect(HOME / "skillrelay.db") as target:
            source.backup(target)
    service = Service(HOME / "skillrelay.db")
    versions = sorted(service.snapshot()["version"], key=lambda v: v["number"])
    first, second = versions[0], versions[1]
    cli("policy", "--mode", "human")
    cli("review", first["id"], first["hash"], "defer", "--reason", "Replay review in isolated demo")
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "skillrelay.cli", "--home", str(HOME), "serve", "--agent", "demo-inspector"],
    )
    async with Client(params) as client:
        chapter(1, "Connect to the real MCP server")
        emit("Workspace: isolated copy of previously generated Hermes evidence.\n", "dim")
        command("MCP tools/list")
        tools = (await client.list_tools()).tools
        emit(f"Connected over stdio. {len(tools)} tools available:")
        for index in range(0, len(tools), 3):
            emit("  " + "  /  ".join(t.name for t in tools[index : index + 3]))
        emit("\nNo browser, dashboard, or REST API.", "yellow")
        time.sleep(3)

        chapter(2, "Read failed and successful actions from a Hermes trace")
        command("MCP list_runs(task='invoice-import')")
        runs = unpack(await client.call_tool("list_runs", {"task": "invoice-import"}))
        original = next(r for r in runs if r["agent"] == "hermes-worker")
        emit(
            f"Run: {original['id']}  |  agent: {original['agent']}"
            f"  |  outcome: {original['outcome']}"
        )
        command(f"MCP get_run_trace(run_id='{original['id']}')")
        trace = unpack(await client.call_tool("get_run_trace", {"run_id": original["id"]}))
        for event in trace["events"]:
            emit(
                f"\n[{event['kind']}] {event['tool']}",
                "yellow" if not event["success"] else "green",
            )
            emit("\n".join(event["result"].splitlines()[-3:]))
        emit("\nThese are captured tool results, not hidden reasoning.", "dim")
        time.sleep(4)

        chapter(3, "Human review gates skill distribution")
        command("MCP discover_skills(task='invoice-import')")
        assert not unpack(await client.call_tool("discover_skills", {"task": "invoice-import"}))
        emit("[]  No active skills available.\n", "yellow")
        command(f"skillrelay inspect '{first['id']}'")
        candidate = json.loads(cli("inspect", first["id"]))
        emit(f"Title:      {candidate['data']['title']}")
        emit(f"State:      {candidate['state']}")
        emit(f"Confidence: {candidate['confidence']}/100 (evidence rubric)")
        emit(f"Evaluator:  {candidate['evaluation']['actor']}")
        emit("Required checks: " + ", ".join(k for k, v in candidate["checks"].items() if v))
        emit("\nHuman mode requires approval even when evaluation passes.", "yellow")
        time.sleep(3)
        command("skillrelay review <version> <exact-content-hash> approve")
        approved = json.loads(
            cli(
                "review",
                first["id"],
                first["hash"],
                "approve",
                "--reason",
                "Scripted operator review of synthetic demo evidence",
            )
        )
        assert approved["state"] == "active"
        emit(f"ACTIVE  {approved['id']}", "green")
        command("MCP discover_skills(task='invoice-import')")
        available = unpack(await client.call_tool("discover_skills", {"task": "invoice-import"}))
        emit(f"{len(available)} active skill: {available[0]['id']}")
        time.sleep(3)

        chapter(4, "A fresh Hermes session retrieves and applies the exact version")
        before = {r["id"] for r in service.snapshot()["run"]}
        command("python examples/hermes/run_demo.py --stage reuse --workspace <isolated-demo>")
        emit("Launching real Hermes with its existing configured model...", "yellow")
        emit(
            "It will discover the skill, retrieve v1, execute the fixture, and report through MCP."
        )
        start = time.monotonic()
        with (OUTPUT / "hermes-driver.log").open("w") as log:
            process = await asyncio.create_subprocess_exec(
                sys.executable,
                str(ROOT / "examples/hermes/run_demo.py"),
                "--stage",
                "reuse",
                "--workspace",
                str(HOME),
                "--profile-root",
                str(OUTPUT / "profiles"),
                stdout=log,
                stderr=subprocess.STDOUT,
            )
            try:
                await asyncio.wait_for(process.wait(), timeout=610)
            except TimeoutError:
                process.terminate()
                await process.wait()
                raise
            if process.returncode:
                raise RuntimeError(f"Hermes failed; see private log in {OUTPUT}")
        elapsed = round(time.monotonic() - start, 2)
        new_run = next(r for r in service.snapshot()["run"] if r["id"] not in before)
        trace = unpack(await client.call_tool("get_run_trace", {"run_id": new_run["id"]}))
        use = next(e for e in trace["events"] if e["kind"] == "skill_use")
        assert use["skill_version"] == first["id"] and use["success"]
        emit(f"\nFresh agent: {new_run['agent']}  |  outcome: {new_run['outcome']}", "green")
        emit(f"Applied exact version: {use['skill_version']}", "green")
        emit(use["result"], "green")
        emit(f"Actual model execution: {elapsed}s. Video playback compresses idle waits.", "dim")
        time.sleep(4)

        chapter(5, "New experience queues learning automatically")
        command("MCP learning_status()")
        status = unpack(await client.call_tool("learning_status", {}))
        queued = [j for j in status["jobs"] if j["status"] == "queued"]
        assert queued
        emit(f"Auto-distillation: {status['policy']['auto_distill']}")
        emit(f"Activation mode:  {status['policy']['mode']}")
        for job in queued:
            emit(f"{job['kind']}: {job['status']}  |  job {job['id']}")
        emit("\nA connected learner claims the evidence; a separate evaluator checks the proposal.")
        emit("SkillRelay provides no server-side model configuration.", "dim")
        time.sleep(3)

        chapter(6, "Inspect a prior revision, activate it, then roll back")
        emit(
            "This second version was generated and evaluated in the earlier real Hermes run.\n",
            "dim",
        )
        command("skillrelay diff <skill>@1 <skill>@2")
        diff = cli("diff", first["id"], second["id"])
        lines = [line for line in diff.splitlines() if line.startswith(("+", "-"))]
        emit("Diff excerpt:")
        for line in lines[:7]:
            emit(line[:98], "green" if line.startswith("+") else "yellow")
        command("skillrelay review <skill>@2 <hash> approve")
        assert (
            json.loads(cli("review", second["id"], second["hash"], "approve"))["state"] == "active"
        )
        emit("Version 2 active. Version 1 retained unchanged.", "green")
        time.sleep(2)
        command("skillrelay review <skill>@1 <hash> rollback")
        assert (
            json.loads(cli("review", first["id"], first["hash"], "rollback"))["state"] == "active"
        )
        emit("Version 1 active again. The decision is recorded in the audit trail.", "green")
        command("skillrelay audit")
        audit = json.loads(cli("audit"))
        for row in [a for a in audit if a["action"] in {"approve", "rollback"}][:3]:
            emit(f"{row['actor']:12}  {row['action']:10}  {row['body']['version']}")
        time.sleep(4)

        chapter(7, "MCP-first learning, end to end")
        command("skillrelay status")
        status = json.loads(cli("status"))
        emit(f"Observed runs: {status['runs']}")
        emit(f"Active skills: {status['active_skills']}")
        emit(f"Queued learning jobs: {status['jobs']['queued']}")
        emit("\nTrace -> distill -> evaluate -> approve -> distribute -> reuse", "cyan")
        emit("\ngithub.com/cfollette18/skillrelay", "green")
        emit("\nSynthetic fixture. Real MCP calls and Hermes execution.", "dim")
        emit("Functional demonstration; no claim of behavioral benchmark improvement.", "dim")
        time.sleep(4)
    snapshot = service.snapshot(reviewer=True)
    report = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "method": "Real MCP/CLI terminal capture with a fresh Hermes reuse session; "
        "earlier Hermes-generated skill versions retained; scripted operator actions",
        "hermes_elapsed_seconds": elapsed,
        "not_a_behavioral_benchmark": True,
        "runs": snapshot["run"],
        "events": snapshot["event"],
        "versions": snapshot["version"],
        "audit": snapshot["audit"],
    }
    (ROOT / "docs/media/demo-evidence.json").write_text(
        json.dumps(clean(report), indent=2).replace(str(ROOT), "$REPO") + "\n"
    )
    (ROOT / ".demo/latest-terminal-workspace.txt").write_text(str(HOME))


if __name__ == "__main__":
    asyncio.run(main())
