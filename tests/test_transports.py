import json
import sys

import pytest
from mcp import Client, StdioServerParameters
from starlette.testclient import TestClient

from skillrelay.server import create_server
from skillrelay.service import Service
from skillrelay.web import create_app


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


def test_http_authorization_and_ingestion(tmp_path):
    service = Service(tmp_path / "db")
    config = {
        "reviewer_token": "reviewer-secret",
        "agent_token": "worker-secret",
        "agents": {"judge": "judge-secret"},
    }
    with TestClient(create_app(service, config), base_url="http://127.0.0.1:8765") as client:
        assert client.get("/health").status_code == 200
        assert client.get("/").status_code == 200
        assert client.get("/api/snapshot").status_code == 401
        assert (
            client.post(
                "/api/policy",
                headers={"Authorization": "Bearer worker-secret"},
                json={"mode": "automatic"},
            ).status_code
            == 401
        )
        headers = {"Authorization": "Bearer reviewer-secret"}
        assert client.get("/api/snapshot", headers=headers).status_code == 200
        assert (
            client.post(
                "/api/policy",
                headers={**headers, "Origin": "https://evil.test"},
                json={"mode": "automatic"},
            ).status_code
            == 403
        )
        assert client.post("/ingest", headers=headers, json={}).status_code == 401
        agent = {"Authorization": "Bearer worker-secret"}
        r = client.post(
            "/ingest", headers=agent, json={"action": "start", "task": "test", "goal": "test"}
        )
        assert r.status_code == 200
        run = r.json()
        assert run["agent"] == "agent"
        r = client.post(
            "/ingest",
            headers={"Authorization": "Bearer judge-secret"},
            json={"action": "finish", "run_id": run["id"], "outcome": "pass"},
        )
        assert r.status_code == 403
        r = client.post(
            "/mcp",
            headers={**agent, "Accept": "application/json, text/event-stream"},
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "integration-test", "version": "1"},
                },
            },
        )
        assert r.status_code == 200, r.text
        assert "result" in json.loads(r.text)


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
            == 401
        )
