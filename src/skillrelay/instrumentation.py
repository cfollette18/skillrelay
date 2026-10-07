"""Small synchronous client for framework hooks. No model/framework dependency."""

import json
import os
import uuid
from pathlib import Path

import httpx

from .safety import clean


class Recorder:
    def __init__(self, url: str, token: str, spool: Path | None = None):
        self.client = httpx.Client(
            base_url=url.rstrip("/"), headers={"Authorization": f"Bearer {token}"}, timeout=5
        )
        self.spool = spool
        if spool:
            spool.mkdir(parents=True, exist_ok=True, mode=0o700)

    def send(self, action: str, **data):
        payload = clean({"action": action, **data})
        response = self.client.post("/ingest", json=payload)
        response.raise_for_status()
        return response.json()

    def start(self, task: str, goal: str, **kwargs):
        return self.send("start", task=task, goal=goal, **kwargs)

    def event(self, run_id: str, action: str, result: str = "", **kwargs):
        event = {"event_id": uuid.uuid4().hex, "action": action, "result": result, **kwargs}
        payload = clean({"action": "event", "run_id": run_id, "event": event})
        # Write before sending. Crash recovery replays the same event_id safely.
        path = self.spool / f"{event['event_id']}.json" if self.spool else None
        if path:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w") as f:
                json.dump(payload, f)
        response = self.client.post("/ingest", json=payload)
        response.raise_for_status()
        if path:
            path.unlink(missing_ok=True)
        return response.json()

    def flush(self):
        if self.spool:
            for path in sorted(self.spool.glob("*.json")):
                response = self.client.post("/ingest", json=json.loads(path.read_text()))
                response.raise_for_status()
                path.unlink()

    def finish(self, run_id: str, outcome: str = "unknown", **kwargs):
        self.flush()
        return self.send("finish", run_id=run_id, outcome=outcome, **kwargs)

    def close(self):
        self.client.close()
