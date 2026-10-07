import sys

import pytest
from mcp import Client, StdioServerParameters
from starlette.testclient import TestClient

from skillrelay.http_transport import create_app
from skillrelay.server import create_server
from skillrelay.service import Service


@pytest.mark.asyncio
async def test_mcp_in_process(tmp_path):
    service = Service(tmp_path / "db")
    async with Client(create_server(service, "worker")) as client:
        tools = await client.list_tools()
        names = {t.name for t in tools.tools}
        assert "propose_skill" in names and "review" not in names
        result = await client.call_tool("start_run", {"task": "test", "goal": "inspect"})
        assert result.structured_content["agent"] == "worker"
        run_id = result.structured_content["id"]
        result = await client.call_tool("finish_run", {"run_id": run_id, "outcome": "unknown"})
        assert result.structured_content["job"]


@pytest.mark.asyncio
async def test_stdio_subprocess(tmp_path):
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "skillrelay.cli", "--home", str(tmp_path), "serve"]
    )
    async with Client(params) as client:
        result = await client.call_tool("learning_status", {})
        assert result.structured_content["policy"]["mode"] == "human"


def test_http_exposes_only_authenticated_mcp(tmp_path):
    service = Service(tmp_path / "db")
    config = {"agent_token": "worker-secret", "agents": {"judge": "judge-secret"}}
    with TestClient(create_app(service, config), base_url="http://127.0.0.1:8765") as client:
        for path in [
            "/",
            "/health",
            "/api/snapshot",
            "/api/review",
            "/ingest",
            "/assets/console.js",
        ]:
            assert client.get(path).status_code == 404
        assert client.post("/mcp", json={}).status_code == 401
        headers = {
            "Authorization": "Bearer worker-secret",
            "Accept": "application/json, text/event-stream",
        }
        assert (
            client.post(
                "/mcp", headers={**headers, "Origin": "https://evil.test"}, json={}
            ).status_code
            == 403
        )
        result = client.post(
            "/mcp",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1"},
                },
            },
        )
        assert result.status_code == 200
        assert "result" in result.json()


def test_http_mcp_carries_authenticated_identity(tmp_path):
    service = Service(tmp_path / "db")
    config = {"reviewer_token": "reviewer", "agent_token": "worker", "agents": {"judge": "judge"}}
    with TestClient(create_app(service, config), base_url="http://127.0.0.1:8765") as client:
        response = client.post(
            "/mcp",
            headers={
                "Authorization": "Bearer judge",
                "Accept": "application/json, text/event-stream",
                "MCP-Protocol-Version": "2025-03-26",
            },
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "start_run",
                    "arguments": {"task": "http", "goal": "Check identity"},
                },
            },
        )
        assert response.status_code == 200
        assert response.json()["result"]["structuredContent"]["agent"] == "judge"
        assert (
            client.post(
                "/api/assess", headers={"Authorization": "Bearer judge"}, json={}
            ).status_code
            == 404
        )


def test_recorder_uses_real_mcp_transport(tmp_path):
    import socket
    import subprocess
    import time

    import httpx

    from skillrelay.instrumentation import Recorder

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    from skillrelay.config import initialize

    config = initialize(tmp_path)
    with (tmp_path / "server.log").open("w") as log:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "skillrelay.cli",
                "--home",
                str(tmp_path),
                "serve",
                "--transport",
                "http",
                "--port",
                str(port),
            ],
            stdout=log,
            stderr=log,
        )
        recorder = Recorder(
            f"http://127.0.0.1:{port}/mcp", config["agent_token"], tmp_path / "spool"
        )
        try:
            for _ in range(100):
                try:
                    if httpx.post(f"http://127.0.0.1:{port}/mcp").status_code == 401:
                        break
                except httpx.TransportError:
                    pass
                time.sleep(0.05)
            run = recorder.start("transport-test", "Record through MCP")
            event = recorder.event(run["id"], "Observe actual output", "PASS", success=True)
            result = recorder.finish(run["id"], "pass", workflow_outcome="pass")
            assert result["job"]
            service = Service(tmp_path / "skillrelay.db")
            assert service.trace(run["id"])["events"][0]["id"] == event["id"]
        finally:
            recorder.close()
            process.terminate()
            process.wait(timeout=10)
