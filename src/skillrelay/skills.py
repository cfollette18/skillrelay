import json
import re


def markdown(version: dict) -> str:
    """Portable skill instructions with immutable source version metadata."""
    d = version["data"]
    lines = [
        "---",
        "name: "
        + json.dumps(
            re.sub(r"[^a-z0-9]+", "-", d["title"].lower()).strip("-")[:64].rstrip("-")
            or "skill-" + version["skill_id"]
        ),
        "description: " + json.dumps(d["summary"][:1024]),
        "---",
        "",
        f"# {d['title']}",
        "",
        d["summary"],
        "",
        "## Applicability",
        "",
    ]
    lines.extend(f"- {item}" for item in d["applicability"])
    lines.extend(["", "## Procedure", ""])
    lines.extend(f"{i}. {step['instruction']}" for i, step in enumerate(d["steps"], 1))
    for label, key in [("Verification", "checks"), ("Limitations", "limitations")]:
        lines.extend(["", f"## {label}", ""])
        lines.extend(f"- {item}" for item in d[key])
    lines.extend(
        [
            "",
            "## Provenance",
            "",
            f"Version: `{version['id']}`",
            f"Content hash: `{version['hash']}`",
            f"Validation: {version['validation']}",
        ]
    )
    return "\n".join(lines) + "\n"
