"""Main entry point for the Plane MCP Server."""

import json
import logging
import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from enum import Enum

import uvicorn
from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware
from starlette.routing import Mount

from plane_mcp.server import get_header_mcp, get_oauth_mcp, get_stdio_mcp


class JSONFormatter(logging.Formatter):
    """JSON log formatter for structured logging (Datadog, ELK, etc.)."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info and record.exc_info[1]:
            log_entry["error"] = {
                "type": type(record.exc_info[1]).__name__,
                "message": str(record.exc_info[1]),
            }
        return json.dumps(log_entry)


def configure_json_logging():
    """Replace FastMCP's Rich handlers with a JSON formatter on the fastmcp logger."""
    fastmcp_logger = logging.getLogger("fastmcp")

    # Remove all existing handlers (Rich)
    for handler in fastmcp_logger.handlers[:]:
        fastmcp_logger.removeHandler(handler)

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(JSONFormatter())
    fastmcp_logger.addHandler(handler)
    fastmcp_logger.setLevel(logging.INFO)
    fastmcp_logger.propagate = False


configure_json_logging()

logger = logging.getLogger("fastmcp.plane_mcp")


class ServerMode(Enum):
    STDIO = "stdio"
    SSE = "sse"
    HTTP = "http"


@asynccontextmanager
async def combined_lifespan(oauth_app, header_app, sse_app):
    """Combine lifespans from OAuth (optional) and Header MCP apps.

    ## fork-custom: oauth_app / sse_app may be ``None`` when
    ``PLANE_OAUTH_PROVIDER_CLIENT_ID`` is unset (header-PAT-only deployment,
    see plane-mcp-v2-deploy N2).
    """
    async with header_app.lifespan(header_app):
        if oauth_app is None:
            yield
            return
        async with oauth_app.lifespan(oauth_app):
            async with sse_app.lifespan(sse_app):
                yield


def main() -> None:
    """Run the MCP server."""
    server_mode = ServerMode.STDIO
    if len(sys.argv) > 1:
        server_mode = ServerMode(sys.argv[1])

    if server_mode == ServerMode.STDIO:
        # Validate API_KEY and PLANE_WORKSPACE_SLUG are set
        if not os.getenv("PLANE_API_KEY"):
            raise ValueError("PLANE_API_KEY is not set")
        if not os.getenv("PLANE_WORKSPACE_SLUG"):
            raise ValueError("PLANE_WORKSPACE_SLUG is not set")

        get_stdio_mcp().run()
        return

    if server_mode == ServerMode.HTTP:
        header_app = get_header_mcp().http_app(stateless_http=True)

        ## fork-custom: OAuth / SSE 는 PLANE_OAUTH_PROVIDER_CLIENT_ID 가 있을
        ## 때만 mount. 팀 공유 배포(Header PAT 전용, spec §2, §3.2)에서는
        ## OAuth client 가 없어 provider 초기화가 실패하므로 skip 한다.
        oauth_app = None
        sse_app = None
        routes = [Mount("/http/api-key", app=header_app)]
        if os.getenv("PLANE_OAUTH_PROVIDER_CLIENT_ID"):
            oauth_mcp = get_oauth_mcp("/http")
            oauth_app = oauth_mcp.http_app(stateless_http=True)
            sse_mcp = get_oauth_mcp()
            sse_app = sse_mcp.http_app(transport="sse")
            routes = [
                *oauth_mcp.auth.get_well_known_routes(mcp_path="/mcp"),
                *sse_mcp.auth.get_well_known_routes(mcp_path="/sse"),
                Mount("/http/api-key", app=header_app),
                Mount("/http", app=oauth_app),
                Mount("/", app=sse_app),
            ]

        app = Starlette(
            routes=routes,
            lifespan=lambda app: combined_lifespan(oauth_app, header_app, sse_app),
        )

        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=False,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # Configure uvicorn loggers to use JSON formatting too
        for uv_logger_name in ("uvicorn", "uvicorn.error"):
            uv_logger = logging.getLogger(uv_logger_name)
            for h in uv_logger.handlers[:]:
                uv_logger.removeHandler(h)
            uv_handler = logging.StreamHandler(sys.stderr)
            uv_handler.setFormatter(JSONFormatter())
            uv_logger.addHandler(uv_handler)

        ## fork-custom: host/port env 우선 — spec §3.3 loopback-only (127.0.0.1) 준수
        host = os.getenv("PLANE_MCP_HTTP_HOST", "0.0.0.0")
        port = int(os.getenv("PLANE_MCP_HTTP_PORT", "8211"))
        logger.info("Starting HTTP server on %s:%d (oauth=%s)", host, port, oauth_app is not None)
        uvicorn.run(
            app,
            host=host,
            port=port,
            log_level="info",
            access_log=False,
        )
        return


if __name__ == "__main__":
    main()
