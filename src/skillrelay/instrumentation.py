"""Synchronous framework recorder backed exclusively by the official MCP client."""

import asyncio
import json
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

from .safety import clean


class Recorder:
    def __init__(self, url: str, token: str, spool: Path | None = None):
        self.url = url.rstrip("/")
        if not self.url.endswith("/mcp"):
            self.url += "/mcp"
        self.token, self.spool = token, spool
        # Hooks may execute inside an existing event loop. Keep SDK I/O on its own thread.
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="skillrelay-recorder")
        if spool:
            spool.mkdir(parents=True, exist_ok=True, mode=0o700)

    async def _request(self, payload):
        methods = {"start": "start_run", "event": "report_event", "finish": "finish_run"}
        method = methods[payload["action"]]
        arguments = {k: v for k, v in payload.items() if k != "action"}
        async with httpx2.AsyncClient(
            headers={"Authorization": f"Bearer {self.token}"}, timeout=10
        ) as http:
            transport = streamable_http_client(self.url, http_client=http)
            async with Client(transport, read_timeout_seconds=15) as client:
                result = await client.call_tool(method, arguments)
                if result.is_error:
                    raise ValueError("MCP recording rejected: " + str(result.content))
                if result.structured_content is None:
                    raise ValueError("MCP recording returned no structured result")
                return result.structured_content

    def _call(self, payload):
        return self._pool.submit(lambda: asyncio.run(self._request(payload))).result()

    def send(self, action: str, **data):
        return self._call(clean({"action": action, **data}))

    def start(self, task: str, goal: str, **kwargs):
        return self.send("start", task=task, goal=goal, **kwargs)

    def event(self, run_id: str, action: str, result: str = "", **kwargs):
        event = {"event_id": uuid.uuid4().hex, "action": action, "result": result, **kwargs}
        payload = clean({"action": "event", "run_id": run_id, "event": event})
        path = self.spool / f"{event['event_id']}.json" if self.spool else None
        if path:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w") as f:
                json.dump(payload, f)
        response = self._call(payload)
        if path:
            path.unlink(missing_ok=True)
        return response

    def flush(self):
        if self.spool:
            for path in sorted(self.spool.glob("*.json")):
                self._call(json.loads(path.read_text()))
                path.unlink()

    def finish(self, run_id: str, outcome: str = "unknown", **kwargs):
        self.flush()
        return self.send("finish", run_id=run_id, outcome=outcome, **kwargs)

    def close(self):
        self._pool.shutdown(wait=True)
