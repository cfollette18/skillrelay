import argparse
import json
import secrets

from .config import initialize, workspace
from .service import Service


def main():
    parser = argparse.ArgumentParser(description="SkillRelay MCP skill learning server")
    parser.add_argument("--home", help="Workspace directory (default ~/.skillrelay)")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init", help="Create private local configuration")
    install = sub.add_parser(
        "install-skill", help="Copy the bundled workflow skill for your client"
    )
    install.add_argument(
        "destination", help="New skill directory; existing paths are not overwritten"
    )
    serve = sub.add_parser("serve", help="Run MCP over stdio or Streamable HTTP")
    serve.add_argument("--transport", choices=["stdio", "http"], default="stdio")
    serve.add_argument(
        "--agent", default="agent", help="Identity for this trusted local stdio process"
    )
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)
    worker = sub.add_parser("work", help="Drive a configured external learning agent")
    worker.add_argument("--command-json", required=True, help='JSON argv array with "{prompt}"')
    worker.add_argument("--kind", choices=["distill", "evaluate"], default="distill")
    worker.add_argument("--once", action="store_true")
    worker.add_argument("--max-invocations", type=int, default=20)
    worker.add_argument("--timeout", type=int, default=300)
    sub.add_parser("status")
    credential = sub.add_parser(
        "credential", help="Print a local credential for setup; keep private"
    )
    credential.add_argument("role", choices=["agent"])
    agent = sub.add_parser("add-agent", help="Provision separate HTTP agent/evaluator identity")
    agent.add_argument("name")
    policy = sub.add_parser("policy")
    policy.add_argument("--mode", choices=["human", "automatic"], required=True)
    policy.add_argument("--threshold", type=int, default=90)
    policy.add_argument("--trust-evaluator", action="append", default=[])
    review = sub.add_parser("review")
    review.add_argument("version")
    review.add_argument("hash")
    review.add_argument(
        "action", choices=["approve", "reject", "defer", "request_changes", "rollback", "revoke"]
    )
    review.add_argument("--reason", default="")
    skills = sub.add_parser("skills", help="List version history for operator review")
    skills.add_argument("--task", default="")
    inspect = sub.add_parser("inspect", help="Inspect an exact historical version")
    inspect.add_argument("version")
    assess = sub.add_parser("assess", help="Record a human assessment from a JSON file")
    assess.add_argument("version")
    assess.add_argument("--file", required=True)
    outcome = sub.add_parser("outcome", help="Human verification of a run's outcome")
    outcome.add_argument("run_id")
    outcome.add_argument("outcome", choices=["pass", "fail", "unknown"])
    dependency = sub.add_parser("dependency", help="Record a changed skill dependency")
    dependency.add_argument("name")
    dependency.add_argument("version")
    dependency.add_argument("--uncertain", action="store_true")
    diff = sub.add_parser("diff", help="Compare immutable skill versions")
    diff.add_argument("left")
    diff.add_argument("right")
    traces = sub.add_parser("traces", help="Inspect observable workflow evidence")
    traces.add_argument("--run", default="")
    sub.add_parser("audit", help="Inspect the operator audit trail")
    sub.add_parser("export", help="Export redacted workspace evidence as JSON")
    args = parser.parse_args()
    if args.command == "install-skill":
        from pathlib import Path
        from shutil import copytree

        destination = Path(args.destination).expanduser()
        source = Path(__file__).parent / "bundled" / "skillrelay-workflow"
        try:
            copytree(source, destination)
        except OSError as exc:
            parser.error(f"Could not install skill: {exc}")
        print(
            f"Workflow skill installed: {destination}\n"
            "Enable it in your MCP client's skills settings."
        )
        return
    home = workspace(args.home)
    config = initialize(home)
    service = Service(home / "skillrelay.db")
    if args.command == "init":
        print(
            f"Workspace ready: {home}\nActivation: {service.policy()['mode']}"
            "\nAuto-distill: enabled"
        )
    elif args.command == "credential":
        print(config[f"{args.role}_token"])
    elif args.command == "add-agent":
        if args.name in {"agent", "human", "system"} or args.name in config.get("agents", {}):
            parser.error("Choose a unique, non-reserved agent name")
        token = secrets.token_urlsafe(32)
        config.setdefault("agents", {})[args.name] = token
        (home / "config.json").write_text(json.dumps(config))
        print(
            f"Agent {args.name} created; restart HTTP server to load credentials. Token:\n{token}"
        )
    elif args.command == "work":
        from .worker import drive

        command = json.loads(args.command_json)
        if not isinstance(command, list) or not all(isinstance(x, str) for x in command):
            parser.error("--command-json must be an array of strings")
        drive(
            service,
            command,
            args.kind,
            args.once,
            max_invocations=args.max_invocations,
            timeout=args.timeout,
        )
    elif args.command == "policy":
        print(
            json.dumps(
                service.set_policy("local-human", args.mode, args.threshold, args.trust_evaluator),
                indent=2,
            )
        )
    elif args.command == "review":
        print(
            json.dumps(
                service.review("local-human", args.version, args.hash, args.action, args.reason),
                indent=2,
            )
        )
    elif args.command == "skills":
        versions = service.snapshot()["version"]
        print(
            json.dumps(
                [
                    {k: v[k] for k in ("id", "hash", "state", "confidence", "task")}
                    for v in versions
                    if not args.task or v["task"] == args.task
                ],
                indent=2,
            )
        )
    elif args.command == "inspect":
        with service.store.connect() as db:
            print(json.dumps(service.store.get(db, "version", args.version), indent=2))
    elif args.command == "assess":
        from pathlib import Path

        from .models import Assessment

        assessment = Assessment.model_validate_json(Path(args.file).read_text())
        print(json.dumps(service.human_assessment(args.version, assessment), indent=2))
    elif args.command == "outcome":
        print(json.dumps({"job": service.verify_outcome("local-human", args.run_id, args.outcome)}))
    elif args.command == "dependency":
        print(
            json.dumps(
                service.dependency("local-human", args.name, args.version, not args.uncertain),
                indent=2,
            )
        )
    elif args.command == "diff":
        print(service.diff(args.left, args.right))
    elif args.command == "traces":
        print(json.dumps(service.trace(args.run) if args.run else service.list_runs(), indent=2))
    elif args.command == "audit":
        print(json.dumps(service.snapshot(reviewer=True)["audit"], indent=2))
    elif args.command == "status":
        snapshot = service.snapshot()
        print(
            json.dumps(
                {
                    "policy": snapshot["policy"],
                    "runs": len(snapshot["run"]),
                    "active_skills": sum(
                        v["state"] == "active" and v["freshness"] == "current"
                        for v in snapshot["version"]
                    ),
                    "jobs": {
                        status: sum(j["status"] == status for j in snapshot["job"])
                        for status in ("queued", "running", "completed", "failed")
                    },
                },
                indent=2,
            )
        )
    elif args.command == "export":
        print(json.dumps(service.snapshot(reviewer=True), indent=2))
    elif args.transport == "stdio":
        from .server import create_server

        create_server(service, args.agent).run()
    else:
        import uvicorn

        from .http_transport import create_app

        uvicorn.run(create_app(service, config), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
