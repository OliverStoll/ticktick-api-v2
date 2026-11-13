"""MCP server wiring: tool registration and transport startup.

Run with `ticktick-mcp` (stdio by default), or `python -m ticktick_v2.mcp`.
"""

import base64
import logging
import secrets
import sys
from typing import Any

from ticktick_v2.mcp.config import McpSettings
from ticktick_v2.mcp.tools import TickTickTools

_ORIGINAL_STREAM_HANDLER_INIT = logging.StreamHandler.__init__

INSTRUCTIONS = """
TickTick access over the unofficial api/v2, the same endpoints the web app uses.

Read tasks, projects, habits and their check-ins, focus (pomodoro) sessions and
calendar events; create, update, complete and delete tasks; record habit
check-ins and backfill focus sessions.

Dates are local wall time: pass "YYYY-MM-DD" for an all-day item and
"YYYY-MM-DDTHH:MM" for a timed one. Task ids are 24-character hex strings, and
the default project is the inbox, whose id is "inbox".
"""

# Tools that stay available in the `essential` profile: reads, plus the
# additive writes that are easy to undo. Destructive and free-form writes are
# full-profile only.
ESSENTIAL_TOOLS = (
    "list_tasks",
    "get_task",
    "list_projects",
    "create_task",
    "complete_task",
    "list_habits",
    "list_habit_checkins",
    "check_in_habit",
    "list_focus_sessions",
    "get_active_focus",
    "list_events",
    "get_login_status",
)

FULL_ONLY_TOOLS = (
    "update_task",
    "set_task_status",
    "delete_task",
    "add_focus_record",
)

ALL_TOOLS = ESSENTIAL_TOOLS + FULL_ONLY_TOOLS


def _redirect_logging_to_stderr() -> None:
    """Keep stdout clean for the JSON-RPC stream.

    The library's loggers are created with a `sys.stdout` stream handler, so a
    single log line there corrupts the stdio transport. Two things are needed:
    move the handlers that already exist, and make sure loggers created later
    (the library builds some lazily, e.g. inside `CookiesManager`) do not open
    a new stdout handler. The second part patches `StreamHandler.__init__`,
    which is process-wide, so this must only be called by the server entrypoint.
    """
    for logger in _all_loggers():
        for handler in logger.handlers:
            if (
                isinstance(handler, logging.StreamHandler)
                and getattr(handler, "stream", None) is sys.stdout
            ):
                handler.setStream(sys.stderr)

    logging.StreamHandler.__init__ = _stream_handler_without_stdout


def _all_loggers() -> list[logging.Logger]:
    loggers = [logging.getLogger()]
    loggers.extend(
        logger
        for logger in logging.Logger.manager.loggerDict.values()
        if isinstance(logger, logging.Logger)
    )
    return loggers


def _stream_handler_without_stdout(self, stream=None) -> None:
    if stream is sys.stdout:
        stream = sys.stderr
    _ORIGINAL_STREAM_HANDLER_INIT(self, stream)


def tool_names_for_profile(profile: str) -> tuple[str, ...]:
    if profile == "essential":
        return ESSENTIAL_TOOLS
    return ALL_TOOLS


def build_server(settings: McpSettings | None = None, tools: TickTickTools | None = None):
    """Build the FastMCP app. Kept import-lazy so the library itself never
    requires the optional `mcp` dependency."""
    try:
        from mcp.server.fastmcp import FastMCP
    except ModuleNotFoundError as e:  # pragma: no cover - depends on install extras
        raise ModuleNotFoundError(
            "The MCP server needs the optional dependency: pip install 'ticktick-py-v2[mcp]'"
        ) from e

    settings = settings or McpSettings.from_env()
    tools = tools or TickTickTools(settings)

    app = FastMCP(name="ticktick", instructions=INSTRUCTIONS.strip())
    for name in tool_names_for_profile(settings.tool_profile):
        app.add_tool(getattr(tools, name), name=name)
    return app


def check_credentials(
    authorization: str | None,
    token: str | None = None,
    username: str | None = None,
    password: str | None = None,
) -> bool:
    """Validate an `Authorization` header against the configured credentials."""
    if not authorization:
        return False
    scheme, _, value = authorization.partition(" ")
    scheme = scheme.lower()
    if token and scheme == "bearer":
        return secrets.compare_digest(value, token)
    if username and password and scheme == "basic":
        try:
            decoded = base64.b64decode(value).decode()
        except (ValueError, UnicodeDecodeError):
            return False
        given_user, _, given_password = decoded.partition(":")
        return secrets.compare_digest(given_user, username) and secrets.compare_digest(
            given_password, password
        )
    return False


def _auth_middleware(app: Any, settings: McpSettings) -> Any:
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.responses import JSONResponse

    class RequireCredentials(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            if not check_credentials(
                request.headers.get("authorization"),
                token=settings.auth_token,
                username=settings.auth_username,
                password=settings.auth_password,
            ):
                return JSONResponse(
                    {"error": "unauthorized"},
                    status_code=401,
                    headers={"WWW-Authenticate": "Basic, Bearer"},
                )
            return await call_next(request)

    return RequireCredentials(app)


def _serve_http(app: Any, settings: McpSettings) -> None:
    import uvicorn

    starlette_app = app.streamable_http_app()
    if settings.requires_auth:
        starlette_app = _auth_middleware(starlette_app, settings)
    uvicorn.run(starlette_app, host=settings.host, port=settings.port, log_level="info")


def main() -> None:
    _redirect_logging_to_stderr()
    settings = McpSettings.from_env()
    app = build_server(settings)
    if settings.transport == "http":
        _serve_http(app, settings)
    else:
        app.run(transport="stdio")


if __name__ == "__main__":
    main()
