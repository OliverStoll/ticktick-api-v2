import pytest

from ticktick_v2.mcp.config import ConfigError, McpSettings, is_loopback


def test_defaults_are_stdio_and_full_profile(monkeypatch):
    for name in ("TICKTICK_TOOL_PROFILE", "TICKTICK_MCP_TRANSPORT", "TICKTICK_MCP_HOST"):
        monkeypatch.delenv(name, raising=False)
    settings = McpSettings.from_env()
    assert settings.transport == "stdio"
    assert settings.tool_profile == "full"
    assert settings.host == "127.0.0.1"
    assert settings.auto_login is False


def test_unknown_tool_profile_is_rejected(monkeypatch):
    monkeypatch.setenv("TICKTICK_TOOL_PROFILE", "tiny")
    with pytest.raises(ConfigError, match="TICKTICK_TOOL_PROFILE"):
        McpSettings.from_env()


def test_unknown_transport_is_rejected(monkeypatch):
    monkeypatch.setenv("TICKTICK_MCP_TRANSPORT", "sse")
    with pytest.raises(ConfigError, match="TICKTICK_MCP_TRANSPORT"):
        McpSettings.from_env()


def test_auto_login_only_for_exact_true(monkeypatch):
    # loose values must not silently start a browser
    for value, expected in (("1", False), ("yes", False), ("TRUE", True), ("true", True)):
        monkeypatch.setenv("TICKTICK_AUTO_LOGIN", value)
        assert McpSettings.from_env().auto_login is expected, value


def test_port_must_be_an_integer(monkeypatch):
    monkeypatch.setenv("TICKTICK_MCP_PORT", "not-a-port")
    with pytest.raises(ConfigError, match="TICKTICK_MCP_PORT"):
        McpSettings.from_env()


def test_username_without_password_is_rejected(monkeypatch):
    monkeypatch.setenv("TICKTICK_MCP_USERNAME", "user")
    with pytest.raises(ConfigError, match="must be set together"):
        McpSettings.from_env()


def test_http_off_loopback_requires_credentials(monkeypatch):
    monkeypatch.setenv("TICKTICK_MCP_TRANSPORT", "http")
    monkeypatch.setenv("TICKTICK_MCP_HOST", "0.0.0.0")
    with pytest.raises(ConfigError, match="without"):
        McpSettings.from_env()

    monkeypatch.setenv("TICKTICK_MCP_TOKEN", "secret")
    assert McpSettings.from_env().requires_auth is True


def test_loopback_http_needs_no_credentials(monkeypatch):
    monkeypatch.setenv("TICKTICK_MCP_TRANSPORT", "http")
    monkeypatch.setenv("TICKTICK_MCP_HOST", "localhost")
    assert McpSettings.from_env().requires_auth is False


@pytest.mark.parametrize(
    ("host", "expected"),
    [("127.0.0.1", True), ("127.1.2.3", True), ("::1", True), ("localhost", True), ("10.0.0.5", False)],
)
def test_is_loopback(host, expected):
    assert is_loopback(host) is expected


def test_cookies_path_prefers_explicit_file(monkeypatch, tmp_path):
    explicit = tmp_path / "exported.json"
    monkeypatch.setenv("TICKTICK_COOKIES_FILE", str(explicit))
    assert McpSettings.from_env().cookies_path == explicit


def test_cookies_path_defaults_into_cookie_store(monkeypatch, tmp_path):
    monkeypatch.delenv("TICKTICK_COOKIES_FILE", raising=False)
    monkeypatch.setenv("TICKTICK_COOKIE_STORE", str(tmp_path))
    settings = McpSettings.from_env()
    assert settings.cookies_path == tmp_path / ".ticktick-cookies.json"


def test_credentials_present_requires_both(monkeypatch):
    monkeypatch.setenv("TICKTICK_EMAIL", "a@b.c")
    monkeypatch.delenv("TICKTICK_PASSWORD", raising=False)
    assert McpSettings.from_env().credentials_present is False
    monkeypatch.setenv("TICKTICK_PASSWORD", "hunter2")
    assert McpSettings.from_env().credentials_present is True
