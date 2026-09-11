"""
Whether this token is still worth using.

A credential the site has rejected outright will not start working on its own,
so continuing to send is pointless: every journal event becomes a round trip
that fails the same way, and the log fills with noise that hides whatever else
is wrong.

The distinction that matters is **terminal or not**, and only the site can make
it. A revoked token is terminal. A database outage is not, and treating it as
one would stop a member's uplink over a bad minute at our end and demand they
generate a token that was never the problem. So this latches on `terminal` from
the API and on nothing else — not on a status code, and never on a response it
does not understand.

Held in memory only. A restart therefore clears the latch and the next event
tries once more, which is the right failure mode: at worst one wasted request,
and a suspension lifted while EDMC was closed simply works again.
"""

import threading

OK = "ok"
# The token is gone or was revoked. Nothing changes until a new one is pasted.
NEEDS_TOKEN = "needs_token"
# The token is real but not allowed to act. An admin lifts it, not the member.
BLOCKED = "blocked"

_NEEDS_TOKEN_CODES = {"no_token", "unknown_token", "revoked"}
_BLOCKED_CODES = {"suspended", "insufficient_scope"}

# Terminal, but about the payload rather than the credential: a malformed body,
# an FID another profile already claims, or a member who has removed themselves
# from the Hall of Fame. None says anything is wrong with the token —
# so latching on them would stop a feed that has no problem at all.
_PAYLOAD_CODES = {"bad_payload", "fid_taken", "hall_of_fame_off"}


class Standing:
    """The uplink's own state, shared between the sender and the UI."""

    def __init__(self):
        self._lock = threading.Lock()
        self._state = OK
        self._code = ""
        self._detail = ""

    @property
    def state(self) -> str:
        with self._lock:
            return self._state

    @property
    def code(self) -> str:
        with self._lock:
            return self._code

    @property
    def detail(self) -> str:
        with self._lock:
            return self._detail

    def is_latched(self) -> bool:
        """Whether sending should stop until something changes."""
        with self._lock:
            return self._state != OK

    def record(self, result) -> bool:
        """
        Files the outcome of one send. Returns True if this latched it.

        A success always clears, including one that arrives after a failure —
        the site is answering again, so whatever was wrong is not any more.
        """
        with self._lock:
            if result.ok:
                self._state, self._code, self._detail = OK, "", ""
                return False

            # Transient by default. Anything the API has not explicitly called
            # terminal — an outage, a timeout, a proxy's HTML error page — is
            # our problem to retry, not the member's to fix.
            if not getattr(result, "terminal", False):
                return False

            code = getattr(result, "code", "") or ""

            if code in _PAYLOAD_CODES:
                return False

            if code in _NEEDS_TOKEN_CODES:
                state = NEEDS_TOKEN
            elif code in _BLOCKED_CODES:
                state = BLOCKED
            else:
                # Terminal, but a reason this build does not know. Stop, since
                # the site said so, but do not tell the member to replace a
                # token when we cannot say that is the problem.
                state = BLOCKED

            already = self._state != OK
            self._state = state
            self._code = code
            self._detail = getattr(result, "detail", "") or ""
            return not already

    def clear(self) -> None:
        """Called when the member changes their token — a new one deserves a try."""
        with self._lock:
            self._state, self._code, self._detail = OK, "", ""
