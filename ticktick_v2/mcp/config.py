"""Environment-driven configuration for the TickTick MCP server.

Every setting is read from the environment so an MCP client can configure the
server in its own `mcpServers` block without a config file. Secrets are never
read from disk: `TICKTICK_PASSWORD` is expected to live in the client's secret
store.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path

TOOL_PROFILES = ("full", "essential")
TRANSPORTS = ("stdio", "http")

_DEFAULT_PORT = 8765


class ConfigError(ValueError):
    """Raised when the MCP server is misconfigured."""


def _env(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None
    value = value.strip()
    return value or None


def _flag(name: str, default: bool = False) -> bool:
    """Read a boolean. Only `true` (case-insensitive) enables it, so a value
    like `yes` or `1` never turns a feature on by accident."""
    value = _env(name)
    if value is None:
        return default
    return value.lower() == "true"


def _int(name: str, default: int, minimum: int | None = None) -> int:
    value = _env(name)
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError as e:
        raise ConfigError(f"{name} must be an integer, got {value!r}") from e
    if minimum is not None and parsed < minimum:
        raise ConfigError(f"{name} must be >= {minimum}, got {parsed}")
    return parsed


def _choice(name: str, default: str, allowed: tuple[str, ...]) -> str:
    value = (_env(name) or default).lower()
    if value not in allowed:
        raise ConfigError(f"{name} must be one of {', '.join(allowed)}, got {value!r}")
    return value


def default_state_dir() -> Path:
    """Where the cached TickTick session lives when no explicit path is set.

    `$XDG_STATE_HOME/ticktick-mcp`, `%LOCALAPPDATA%/ticktick-mcp` on Windows,
    and `~/.local/state/ticktick-mcp` otherwise.
    """
    xdg_state = _env("XDG_STATE_HOME")
    if xdg_state:
        return Path(xdg_state) / "ticktick-mcp"
    if os.name == "nt":
        local_appdata = _env("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(local_appdata) / "ticktick-mcp"
    return Path.home() / ".local" / "state" / "ticktick-mcp"


def is_loopback(host: str) -> bool:
    return host in {"127.0.0.1", "::1", "localhost"} or host.startswith("127.")


@dataclass(frozen=True)
class McpSettings:
    tool_profile: str = "full"
    transport: str = "stdio"
    host: str = "127.0.0.1"
    port: int = _DEFAULT_PORT
    auth_username: str | None = None
    auth_password: str | None = None
    auth_token: str | None = None
    cookies_file: Path | None = None
    cookie_store: Path = field(default_factory=default_state_dir)
    auto_login: bool = False
    headless: bool = True
    timezone: str | None = None

    @classmethod
    def from_env(cls) -> "McpSettings":
        settings = cls(
            tool_profile=_choice("TICKTICK_TOOL_PROFILE", "full", TOOL_PROFILES),
            transport=_choice("TICKTICK_MCP_TRANSPORT", "stdio", TRANSPORTS),
            host=_env("TICKTICK_MCP_HOST") or "127.0.0.1",
            port=_int("TICKTICK_MCP_PORT", _DEFAULT_PORT, minimum=1),
            auth_username=_env("TICKTICK_MCP_USERNAME"),
            auth_password=_env("TICKTICK_MCP_PASSWORD"),
            auth_token=_env("TICKTICK_MCP_TOKEN"),
            cookies_file=Path(_env("TICKTICK_COOKIES_FILE")) if _env("TICKTICK_COOKIES_FILE") else None,
            cookie_store=Path(_env("TICKTICK_COOKIE_STORE") or default_state_dir()),
            auto_login=_flag("TICKTICK_AUTO_LOGIN"),
            headless=_flag("TICKTICK_HEADLESS", default=True),
            timezone=_env("TICKTICK_TIMEZONE"),
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        if (self.auth_username is None) != (self.auth_password is None):
            raise ConfigError(
                "TICKTICK_MCP_USERNAME and TICKTICK_MCP_PASSWORD must be set together"
            )
        if self.transport == "http" and not is_loopback(self.host) and not self.requires_auth:
            raise ConfigError(
                "Refusing to expose the HTTP transport off loopback without "
                "TICKTICK_MCP_TOKEN or TICKTICK_MCP_USERNAME/TICKTICK_MCP_PASSWORD"
            )

    @property
    def requires_auth(self) -> bool:
        return bool(self.auth_token or (self.auth_username and self.auth_password))

    @property
    def cookies_path(self) -> Path:
        """Cookies file to read, and to write after a login."""
        return self.cookies_file or self.cookie_store / ".ticktick-cookies.json"

    @property
    def credentials_present(self) -> bool:
        return bool(_env("TICKTICK_EMAIL") and _env("TICKTICK_PASSWORD"))
