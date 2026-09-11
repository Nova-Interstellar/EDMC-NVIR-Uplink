"""
What this commander has done, as the game counts it.

Elite writes one journal event, `Statistics`, holding every lifetime total it
tracks: sixteen sections and roughly two hundred numbers, arriving together.
That is the whole of the squadron Hall of Fame's data, and it costs nothing to
collect because the game was writing it anyway.

Like the identity handshake, this is state rather than a stream. The numbers
only move while you play, and the event is already cumulative, so there is
nothing to accumulate here — the plugin forwards the latest one and the site
keeps exactly one per member.

Sent whole, deliberately. The site decides which numbers become boards, so
sending everything is what lets NVIR add a board without shipping a new plugin.
The member's only decision is whether to take part at all, which is one setting
rather than sixteen.
"""

import json
from typing import Optional

# The event carries a timestamp and its own name; neither is a statistic.
_DROP = ("timestamp", "event")


class Statistics:
    """The last statistics seen, and the last the site accepted."""

    def __init__(self):
        self._latest: Optional[dict] = None
        self._sent: Optional[str] = None
        # Set when the site says it will not take these — the member removed
        # their record from their profile. Cleared on a new token, since that is
        # a different profile as far as the site is concerned.
        self._refused = False

    def forget(self) -> None:
        """A new token deserves a fresh submission, and clears a refusal."""
        self._sent = None
        self._refused = False

    def summary(self) -> str:
        """One line for the diagnostics report."""
        if self._refused:
            return "refused by the site (Hall of Fame is off on the profile)"
        if self._latest is None:
            return "not observed yet (no Statistics entry this session)"

        return "{0} sections seen, {1}".format(
            len(self._latest),
            "accepted by the site" if self._sent else "not yet accepted",
        )

    def pending(self) -> Optional[dict]:
        """
        The last totals seen, if the site has not already taken them.

        Same reason as the handshake: `observe` can only answer while a
        `Statistics` entry is in hand, and the game decides when to write one.
        A member who pastes their token just after the last of the session
        would otherwise contribute nothing until they play again.
        """
        if self._refused or self._latest is None:
            return None

        payload = {"v": 1, "statistics": self._latest}
        if _fingerprint(payload) == self._sent:
            return None
        return payload

    def accept(self, payload: dict) -> None:
        """Called once the site has stored a payload, so it is not repeated."""
        self._sent = _fingerprint(payload)

    def refuse(self) -> None:
        """
        Called when the site refuses outright.

        A member who has deleted their record has said no, and the plugin should
        stop asking for the rest of the session rather than posting the same
        refusal at every login.
        """
        self._refused = True

    def observe(self, entry: dict) -> Optional[dict]:
        """
        Folds one journal entry in. Returns a payload worth sending, or None.

        `Statistics` fires far more often than it changes — measured at up to
        thirty-two times in a single session — so the comparison is against what
        was last accepted, not against whether we have seen one.
        """
        if entry.get("event") != "Statistics":
            return None
        if self._refused:
            return None

        sections = {
            name: value
            for name, value in entry.items()
            if name not in _DROP and isinstance(value, dict)
        }
        if not sections:
            return None

        self._latest = sections
        return self.pending()

    @property
    def latest(self) -> Optional[dict]:
        """The sections last seen, whether or not the site has taken them."""
        return self._latest


def _fingerprint(payload: dict) -> str:
    """
    A stable string for "are these the same numbers".

    Two hundred fields compared by value would be a dictionary walk per journal
    entry; sorted JSON is one hash and cannot disagree with itself about key
    order the way a plain `==` on rebuilt dictionaries can.
    """
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))
