import asyncio
import base64
import logging
import sys

import pytest

from ticktick_v2.mcp.config import McpSettings
from ticktick_v2.mcp.server import (
    _ORIGINAL_STREAM_HANDLER_INIT,
    ALL_TOOLS,
    ESSENTIAL_TOOLS,
    _redirect_logging_to_stderr,
    check_credentials,
    tool_names_for_profile,
)


def test_essential_profile_is_a_subset_of_full():
    assert set(ESSENTIAL_TOOLS) <= set(ALL_TOOLS)
    assert "delete_task" not in ESSENTIAL_TOOLS
    assert "delete_task" in ALL_TOOLS


def test_tool_names_for_profile():
    assert tool_names_for_profile("essential") == ESSENTIAL_TOOLS
    assert tool_names_for_profile("full") == ALL_TOOLS


def test_bearer_token():
    assert check_credentials("Bearer s3cret", token="s3cret") is True
    assert check_credentials("Bearer wrong", token="s3cret") is False
    assert check_credentials(None, token="s3cret") is False


def test_basic_auth():
    encoded = base64.b64encode(b"user:pass").decode()
    assert check_credentials(f"Basic {encoded}", username="user", password="pass") is True
    assert check_credentials(f"Basic {encoded}", username="user", password="other") is False
    assert check_credentials("Basic !!!not-base64", username="user", password="pass") is False


def test_unknown_scheme_is_rejected():
    assert check_credentials("Digest abc", token="s3cret") is False


def test_redirect_logging_moves_stdout_handlers(monkeypatch):
    logger = logging.getLogger("ticktick-mcp-test-logger")
    handler = logging.StreamHandler(sys.stdout)
    logger.addHandler(handler)

    monkeypatch.setattr(logging.StreamHandler, "__init__", _ORIGINAL_STREAM_HANDLER_INIT)
    _redirect_logging_to_stderr()

    assert handler.stream is sys.stderr
    logger.removeHandler(handler)


def test_redirect_logging_covers_later_handlers(monkeypatch):
    # loggers the library creates lazily must not reopen a stdout handler
    monkeypatch.setattr(logging.StreamHandler, "__init__", _ORIGINAL_STREAM_HANDLER_INIT)
    _redirect_logging_to_stderr()

    late_handler = logging.StreamHandler(sys.stdout)
    assert late_handler.stream is sys.stderr


def test_build_server_registers_tools_per_profile():
    pytest.importorskip("mcp")
    from ticktick_v2.mcp.server import build_server

    app = build_server(McpSettings(tool_profile="essential"), tools=_StubTools())
    names = {tool.name for tool in asyncio.run(app.list_tools())}
    assert names == set(ESSENTIAL_TOOLS)


class _StubTools:
    """Every attribute `build_server` looks up resolves to a no-arg callable."""

    def __getattr__(self, name):
        def tool(**kwargs):
            """Return the tool name."""
            return {"tool": name}

        return tool
