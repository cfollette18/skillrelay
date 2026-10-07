"""A workspace has its own database and a separate reviewer credential."""

import json
import os
import secrets
from pathlib import Path


def workspace(path: str | None = None) -> Path:
    return Path(path or os.environ.get("SKILLRELAY_HOME", "~/.skillrelay")).expanduser()


def initialize(home: Path) -> dict:
    home.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = home / "config.json"
    if not path.exists():
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(
                {
                    "reviewer_token": secrets.token_urlsafe(32),
                    "agent_token": secrets.token_urlsafe(32),
                },
                f,
            )
    return json.loads(path.read_text())
