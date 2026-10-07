"""Export only the synthetic demo evidence; never profile credentials or raw model logs."""

import json
from datetime import datetime, timezone
from pathlib import Path

from skillrelay.safety import clean
from skillrelay.service import Service

ROOT = Path(__file__).resolve().parents[2]
service = Service(ROOT / ".demo/workspace/skillrelay.db")
snapshot = service.snapshot(reviewer=True)
assert all(r["task"] == "invoice-import" for r in snapshot["run"]), "Not a demo-only workspace"
report = {
    "captured_at": datetime.now(timezone.utc).isoformat(),
    "method": "Live Hermes sessions via MCP; synthetic fixture; scripted reviewer actions",
    "not_a_behavioral_benchmark": True,
    "redactions": ["Absolute repository path replaced with $REPO", "Job lease tokens omitted"],
    "runs": snapshot["run"],
    "workflows": snapshot["workflow"],
    "events": snapshot["event"],
    "versions": snapshot["version"],
    "audit": snapshot["audit"],
}
text = json.dumps(clean(report), indent=2).replace(str(ROOT), "$REPO")
output = ROOT / "docs/media/demo-evidence.json"
output.write_text(text + "\n")
print(f"Exported {len(snapshot['run'])} real runs and {len(snapshot['version'])} versions")
