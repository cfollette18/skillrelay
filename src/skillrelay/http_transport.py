"""Authenticated Streamable HTTP transport. The only endpoint is /mcp."""

import hmac

from starlette.requests import Request
from starlette.responses import JSONResponse

from .server import create_server, principal


class Authentication:
    def __init__(self, app, config):
        self.app = app
        self.agents = {"agent": config["agent_token"], **config.get("agents", {})}

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        if scope["path"] != "/mcp":
            return await JSONResponse({"error": "Not found"}, status_code=404)(scope, receive, send)
        request = Request(scope)
        supplied = request.headers.get("authorization", "").removeprefix("Bearer ").encode()
        actor = next(
            (
                name
                for name, token in self.agents.items()
                if hmac.compare_digest(supplied, token.encode())
            ),
            None,
        )
        if actor is None:
            return await JSONResponse({"error": "Unauthorized"}, status_code=401)(
                scope, receive, send
            )
        origin = request.headers.get("origin")
        if origin and origin != f"{request.url.scheme}://{request.url.netloc}":
            return await JSONResponse({"error": "Cross-origin request rejected"}, status_code=403)(
                scope, receive, send
            )
        token = principal.set(actor)
        try:
            await self.app(scope, receive, send)
        finally:
            principal.reset(token)


def create_app(service, config):
    server = create_server(service)
    return Authentication(
        server.streamable_http_app(stateless_http=True, json_response=True), config
    )
