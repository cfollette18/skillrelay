"""Hermes adapter. Install skillrelay-mcp in Hermes' Python environment first.

Set SKILLRELAY_URL and SKILLRELAY_AGENT_TOKEN. No reviewer credential is needed.
Tool outputs are untrusted evidence; this hook never captures reasoning callbacks.
"""

import json
import logging
import os
import threading
from pathlib import Path

logger = logging.getLogger(__name__)
_lock = threading.Lock()
_runs = {}
_recorder = None


def recorder():
    global _recorder
    if _recorder is None:
        from skillrelay.instrumentation import Recorder

        token = os.environ.get("SKILLRELAY_AGENT_TOKEN")
        if not token:
            return None
        _recorder = Recorder(
            os.environ.get("SKILLRELAY_URL", "http://127.0.0.1:8765/mcp"),
            token,
            Path(os.environ.get("HERMES_HOME", "~/.hermes")).expanduser() / "skillrelay-spool",
        )
    return _recorder


def post_tool_call(*, tool_name="", args=None, result=None, session_id="", task_id="", **kwargs):
    # Never recursively capture SkillRelay reporting, job leases, or credentials.
    if "skillrelay" in tool_name.lower():
        return
    with _lock:
        try:
            client = recorder()
            if not client:
                return
            key = session_id or task_id or "local"
            if key not in _runs:
                _runs[key] = client.start(
                    os.environ.get("SKILLRELAY_TASK", "hermes-workflow"),
                    "Hermes observable tool workflow",
                )["id"]
            client.event(
                _runs[key],
                json.dumps(args, default=str)[:4000],
                json.dumps(result, default=str)[:4000],
                tool=tool_name,
                kind="step",
            )
        except Exception as exc:
            logger.warning(
                "SkillRelay capture unavailable (%s); event spool retained", type(exc).__name__
            )


def on_session_end(session_id="", completed=True, interrupted=False, **kwargs):
    with _lock:
        key = session_id or "local"
        run_id = _runs.get(key)
        if not run_id:
            return
        try:
            # Transport completion does not prove that the user's task succeeded.
            recorder().finish(run_id, "unknown")
            del _runs[key]
        except Exception as exc:
            logger.warning("SkillRelay completion unavailable (%s)", type(exc).__name__)


def register(ctx):
    ctx.register_hook("post_tool_call", post_tool_call)
    ctx.register_hook("on_session_end", on_session_end)
