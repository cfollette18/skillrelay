"""Local console and authenticated HTTP transport. Bind to loopback by default."""

import hmac
from contextlib import asynccontextmanager
from pathlib import Path

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse
from starlette.routing import Mount, Route

from .models import Event
from .server import create_server, principal


class Authentication:
    def __init__(self, app, config):
        self.app, self.config = app, config

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["path"] in {"/", "/health"}:
            return await self.app(scope, receive, send)
        request = Request(scope)
        supplied = request.headers.get("authorization", "").removeprefix("Bearer ")
        reviewer = hmac.compare_digest(supplied, self.config["reviewer_token"])
        agents = {"agent": self.config["agent_token"], **self.config.get("agents", {})}
        actor = next(
            (name for name, token in agents.items() if hmac.compare_digest(supplied, token)), None
        )
        is_review = scope["path"].startswith("/api/")
        # Reviewer credential is intentionally not usable as an agent credential.
        if (is_review and not reviewer) or (not is_review and not actor):
            return await JSONResponse({"error": "Unauthorized"}, status_code=401)(
                scope, receive, send
            )
        origin = request.headers.get("origin")
        if origin and origin != f"{request.url.scheme}://{request.url.netloc}":
            return await JSONResponse({"error": "Cross-origin request rejected"}, status_code=403)(
                scope, receive, send
            )
        token = principal.set("human" if reviewer else actor)
        try:
            await self.app(scope, receive, send)
        finally:
            principal.reset(token)


def create_app(service, config):
    mcp = create_server(service)
    transport = mcp.streamable_http_app(stateless_http=True, json_response=True)

    @asynccontextmanager
    async def lifespan(app):
        async with mcp.session_manager.run():
            yield

    async def home(request):
        return HTMLResponse(
            Path(__file__).with_name("dashboard.html").read_text(),
            headers={
                "Content-Security-Policy": (
                    "default-src 'self'; script-src 'unsafe-inline'; "
                    "style-src 'unsafe-inline'; connect-src 'self'; "
                    "frame-ancestors 'none'"
                ),
                "X-Content-Type-Options": "nosniff",
                "Cache-Control": "no-store",
            },
        )

    async def health(request):
        return JSONResponse({"status": "ok", "service": "SkillRelay"})

    async def api(request):
        try:
            op = request.path_params["op"]
            data = await request.json() if request.method == "POST" else {}
            if op == "snapshot":
                result = service.snapshot(reviewer=True)
            elif op == "review" and request.method == "POST":
                result = service.review("human", **data)
            elif op == "policy" and request.method == "POST":
                result = service.set_policy("human", **data)
            elif op == "outcome" and request.method == "POST":
                result = service.verify_outcome("human", **data)
            elif op == "dependency" and request.method == "POST":
                result = service.dependency("human", **data)
            elif op == "diff":
                result = service.diff(request.query_params["left"], request.query_params["right"])
            else:
                return JSONResponse({"error": "Unknown operation"}, status_code=404)
            return JSONResponse(result, headers={"Cache-Control": "no-store"})
        except (ValueError, KeyError, TypeError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        except PermissionError as exc:
            return JSONResponse({"error": str(exc)}, status_code=403)

    async def ingest(request):
        try:
            data = await request.json()
            action = data.pop("action")
            actor = principal.get()
            if action == "start":
                result = service.start(actor, **data)
            elif action == "event":
                result = service.event(actor, data["run_id"], Event.model_validate(data["event"]))
            elif action == "finish":
                result = service.finish(actor, **data)
            else:
                raise ValueError("Unknown ingestion action")
            return JSONResponse(result)
        except (ValueError, KeyError, TypeError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        except PermissionError as exc:
            return JSONResponse({"error": str(exc)}, status_code=403)

    app = Starlette(
        routes=[
            Route("/", home),
            Route("/health", health),
            Route("/api/{op}", api, methods=["GET", "POST"]),
            Route("/ingest", ingest, methods=["POST"]),
            Mount("/", transport),
        ],
        lifespan=lifespan,
    )
    return Authentication(app, config)
