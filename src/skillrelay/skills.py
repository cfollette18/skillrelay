import json


def markdown(version: dict) -> str:
    """Portable skill instructions with immutable source version metadata."""
    d = version["data"]
    lines = [
        "---",
        "name: " + json.dumps(d["title"]),
        "description: " + json.dumps(d["summary"]),
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
