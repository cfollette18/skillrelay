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
    serve = sub.add_parser("serve", help="Run MCP stdio or HTTP plus dashboard")
    serve.add_argument("--transport", choices=["stdio", "http"], default="stdio")
    serve.add_argument(
        "--agent", default="agent", help="Identity for this trusted local stdio process"
    )
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)
    sub.add_parser("status")
    credential = sub.add_parser(
        "credential", help="Print a local credential for setup; keep private"
    )
    credential.add_argument("role", choices=["agent", "reviewer"])
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
    sub.add_parser("export", help="Export redacted workspace evidence as JSON")
    args = parser.parse_args()
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
    elif args.command in {"status", "export"}:
        print(json.dumps(service.snapshot(reviewer=True), indent=2))
    elif args.transport == "stdio":
        from .server import create_server

        create_server(service, args.agent).run()
    else:
        import uvicorn

        from .web import create_app

        uvicorn.run(create_app(service, config), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
