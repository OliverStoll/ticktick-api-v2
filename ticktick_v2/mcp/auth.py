"""Session handling for the MCP server.

The library's functions each accept optional auth headers and otherwise log in
through Selenium. A long-lived MCP server wants neither: it should authenticate
once, reuse the cached session for every tool call, and never launch a browser
unless the operator asked for it.
"""

import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from ticktick_v2.cookies_login import build_cookies_manager, get_authenticated_ticktick_headers
from ticktick_v2.mcp.config import McpSettings
from ticktick_v2.utils.logger import create_logger

log = create_logger("TickTick MCP Auth")

LOGIN_HINT = (
    "No usable TickTick session. Either export cookies from a logged-in browser into "
    "TICKTICK_COOKIES_FILE, or set TICKTICK_AUTO_LOGIN=true together with "
    "TICKTICK_EMAIL and TICKTICK_PASSWORD to allow the headless Selenium login."
)


class AuthError(RuntimeError):
    """Raised when no usable TickTick session can be obtained."""


def _headers_from_cookies(cookies: str, base_headers: dict) -> dict:
    headers = base_headers.copy()
    headers["Cookie"] = cookies
    if "_csrf_token" in cookies:  # TickTick wants the CSRF token in its own header
        headers["X-Crsftoken"] = cookies.split("_csrf_token=")[1].split(";")[0]
    return headers


@dataclass
class LoginStatus:
    cookies_path: Path
    cookies_present: bool
    cookies_valid: bool | None
    cookie_age_days: float | None
    auto_login: bool
    credentials_present: bool


class SessionCache:
    """Holds the headers for the lifetime of the server process."""

    def __init__(self, settings: McpSettings) -> None:
        self.settings = settings
        self._headers: dict | None = None
        self._lock = threading.Lock()

    def headers(self) -> dict:
        with self._lock:
            if self._headers is not None:
                return self._headers
            self._headers = self._resolve_headers()
            return self._headers

    def invalidate(self) -> None:
        """Forget the cached session after a 401 so the next call re-reads it."""
        with self._lock:
            self._headers = None

    def _resolve_headers(self) -> dict:
        manager = build_cookies_manager(
            cookies_path=str(self.settings.cookies_path),
            headless=self.settings.headless,
        )
        cookies = manager.get_cookies_from_file()
        if cookies and manager.test_cookies_valid(cookies):
            log.debug(f"Using cookies from {self.settings.cookies_path}")
            return _headers_from_cookies(cookies, manager.headers)

        if not self.settings.auto_login:
            raise AuthError(LOGIN_HINT)
        if not self.settings.credentials_present:
            raise AuthError(
                "TICKTICK_AUTO_LOGIN is true but TICKTICK_EMAIL and TICKTICK_PASSWORD are not "
                "both set. " + LOGIN_HINT
            )

        log.info("Cached cookies are missing or expired; logging in through Selenium")
        return get_authenticated_ticktick_headers(
            cookies_path=str(self.settings.cookies_path),
            headless=self.settings.headless,
        )

    def status(self, check_network: bool = False) -> LoginStatus:
        """Report the cached session without logging in. `check_network` runs
        the same cookie test the login path uses, which costs one request."""
        path = self.settings.cookies_path
        manager = build_cookies_manager(cookies_path=str(path), headless=self.settings.headless)
        cookies = manager.get_cookies_from_file()
        age_days = None
        if path.exists():
            modified = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
            age_days = round((datetime.now(UTC) - modified).total_seconds() / 86400, 2)

        valid: bool | None = None
        if check_network and cookies:
            valid = manager.test_cookies_valid(cookies)

        return LoginStatus(
            cookies_path=path,
            cookies_present=bool(cookies),
            cookies_valid=valid,
            cookie_age_days=age_days,
            auto_login=self.settings.auto_login,
            credentials_present=self.settings.credentials_present,
        )
