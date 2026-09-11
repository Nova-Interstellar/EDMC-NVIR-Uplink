"""
Delivery to the squadron API.

The plugin is a transport and nothing more: it normalises a journal entry and
hands it to nova-web, which checks it against the roster, applies the
thresholds, renders the embed and posts it. No Discord webhook URL ever lives
on a member's machine, so a leaked EDMC config cannot post to the channel and
an edited plugin cannot widen what reaches it.
"""

from dataclasses import dataclass
from typing import Optional

try:
    import requests  # type: ignore

    REQUESTS_AVAILABLE = True
except ImportError:  # pragma: no cover - EDMC ships requests
    REQUESTS_AVAILABLE = False

from .config import (
    API_EVENTS_PATH,
    API_IDENTITY_PATH,
    API_STATS_PATH,
    HTTP_TIMEOUT,
    PLUGIN_VERSION,
    USER_AGENT,
)


@dataclass
class Delivery:
    """The outcome of one send attempt."""

    ok: bool
    status: int = 0
    detail: str = ""
    retry_after: float = 0.0
    retryable: bool = False
    # The API's own verdict, when it sends one. `code` names the reason;
    # `terminal` says the credential will not start working on its own.
    #
    # Both default to "absent" on purpose. A proxy, a captive portal or a
    # platform error page can answer 4xx with HTML, and treating that as a
    # terminal refusal would discard a token that was never wrong.
    code: str = ""
    terminal: bool = False
    # Decoded JSON response. The API replies with its own verdict even on
    # success - an event can be accepted and still go unposted for falling
    # under a threshold - and echoes the rendered embed for debug sends.
    body: Optional[dict] = None


def _clip(text: str, limit: int) -> str:
    text = str(text)
    return text if len(text) <= limit else text[: limit - 1] + "\N{HORIZONTAL ELLIPSIS}"


class ApiTransport:
    """Posts normalised payloads to nova-web."""

    name = "api"

    def __init__(self, settings):
        self._settings = settings
        self._session = None
        if REQUESTS_AVAILABLE:
            self._session = requests.Session()
            self._session.headers.update(
                {"User-Agent": USER_AGENT, "Content-Type": "application/json"}
            )

    def close(self) -> None:
        if self._session is not None:
            self._session.close()
            self._session = None

    def url(self) -> str:
        return self._path(API_EVENTS_PATH)

    def identity_url(self) -> str:
        return self._path(API_IDENTITY_PATH)

    def stats_url(self) -> str:
        return self._path(API_STATS_PATH)

    def _path(self, path: str) -> str:
        base = self._settings.base_url().rstrip("/")
        return base + path if base else ""

    def target(self) -> str:
        base = self._settings.base_url()
        if not base:
            return "no endpoint set"
        return base + " (dev)" if self._settings.is_dev_endpoint() else base

    def is_ready(self) -> bool:
        """The endpoint ships with the plugin; only the token is missing-able."""
        return bool(self._settings.api_token_value)

    def send(self, payload: dict) -> Delivery:
        result = self._authorised(self.url(), payload)

        # A 2xx only means the API accepted the event. It still decides whether
        # the event was worth posting, so report its verdict rather than ours.
        if result.ok and result.body is not None:
            verdict = "Posted" if result.body.get("posted") else "Accepted, not posted"
            reason = str(result.body.get("reason") or "").strip()
            result.detail = (
                "{0} \N{EM DASH} {1}".format(verdict, reason) if reason else verdict
            )

        return result

    def send_identity(self, payload: dict) -> Delivery:
        """
        The handshake, to its own endpoint on the same credential.

        Kept apart from `send` because success means different things: an event
        can be accepted and still go unposted for falling under a threshold,
        while a recorded identity is simply recorded.
        """
        result = self._authorised(self.identity_url(), payload)

        if result.ok:
            name = ""
            if result.body is not None:
                name = str(result.body.get("commanderName") or "").strip()
            result.detail = (
                "Identity confirmed \N{EM DASH} {0}".format(name)
                if name
                else "Identity confirmed"
            )

        return result

    def send_statistics(self, payload: dict) -> Delivery:
        """
        Commander statistics, for the Hall of Fame.

        Its own endpoint because it is neither an event nor an identity: the
        site stores it whole and decides later which numbers become boards.
        """
        result = self._authorised(self.stats_url(), payload)

        if result.ok:
            sections = ""
            if result.body is not None:
                sections = str(result.body.get("sections") or "").strip()
            result.detail = (
                "Statistics stored \N{EM DASH} {0} sections".format(sections)
                if sections
                else "Statistics stored"
            )

        return result

    def _authorised(self, url: str, payload: dict) -> Delivery:
        """Everything both endpoints do the same way: endpoint, token, headers."""
        if not url:
            # Dev mode with an empty endpoint. Named rather than lumped in with
            # a generic failure, because the fix is one field away and nothing
            # about the token is wrong.
            return Delivery(
                False,
                detail="Dev mode is on but no endpoint is set.",
                code="no_endpoint",
            )

        token = self._settings.api_token_value
        if not token:
            return Delivery(False, detail="No squadron token configured")

        return self._post(
            url,
            payload,
            {
                "Authorization": "Bearer {0}".format(token),
                "X-NVIR-Plugin": PLUGIN_VERSION,
            },
        )

    def _post(self, url: str, body: dict, headers: dict) -> Delivery:
        if not REQUESTS_AVAILABLE:
            return Delivery(False, detail="The requests library is unavailable")

        if self._session is None:
            return Delivery(False, detail="Transport is closed")

        try:
            response = self._session.post(
                url, json=body, headers=headers, timeout=HTTP_TIMEOUT
            )
        except Exception as err:  # network unreachable, DNS, TLS, timeout
            return Delivery(False, detail=str(err), retryable=True, retry_after=5.0)

        status = response.status_code

        if 200 <= status < 300:
            decoded = None
            try:
                decoded = response.json()
            except Exception:
                pass
            return Delivery(
                True,
                status=status,
                detail="Delivered",
                body=decoded if isinstance(decoded, dict) else None,
            )

        if status == 429:
            retry_after = 5.0
            try:
                retry_after = float(response.headers.get("Retry-After", retry_after))
            except (TypeError, ValueError):
                pass
            return Delivery(
                False,
                status=status,
                detail="Rate limited",
                retryable=True,
                retry_after=retry_after,
            )

        if status >= 500:
            return Delivery(
                False,
                status=status,
                detail="Server error",
                retryable=True,
                retry_after=5.0,
            )

        # The API reports why it refused; fall back to the raw body otherwise.
        detail = response.text
        code = ""
        terminal = False

        try:
            refused = response.json()
            if isinstance(refused, dict):
                if refused.get("error"):
                    detail = str(refused["error"])
                code = str(refused.get("code") or "")
                terminal = bool(refused.get("terminal"))
        except Exception:
            pass

        return Delivery(
            False,
            status=status,
            detail=_clip(detail, 300),
            code=code,
            terminal=terminal,
        )


def build(settings) -> ApiTransport:
    return ApiTransport(settings)
