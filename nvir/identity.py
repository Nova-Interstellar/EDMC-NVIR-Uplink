"""
Who this commander is, as the game says it.

The feed proves a token is good. This proves the *commander* is: the Frontier
id, the name attached to it, and whether they are flying under the squadron tag.
None of it can be established anywhere else — Discord has never heard of an FID,
Inara reports a name a human typed into a form, and neither can show the two
belong together. A journal can.

It is state, not a stream, so it is not sent per event. The commander's name and
FID arrive once at login and then never change for the rest of the session;
squadron standing changes a handful of times a year. So this watches the few
events that carry those facts, and offers a payload only when what it knows has
actually moved. In a normal session that is one request, at login.

Nothing here is private. The FID, the commander name and the squadron are all
things the game already shows to anyone in the same instance.
"""

from typing import Optional

# "Not observed" — distinct from "observed to be in no squadron", which is None.
#
# The difference decides whether the site touches stored standing at all.
# `SquadronStartup` only fires for a commander who is in one, so a plugin that
# has not seen it cannot tell "no squadron" from "not looked yet" — and guessing
# would empty the roster every time somebody starts EDMC before the game.
_UNSET = object()

# Carry the commander's own identity. `Commander` spells the name `Name`,
# `LoadGame` spells it `Commander`; both carry `FID`.
_NAME_EVENTS = ("Commander", "LoadGame")

# Carry squadron standing. Every one of them names the squadron and none of them
# numbers it, which is why the site matches on the name.
_SQUADRON_EVENTS = (
    "SquadronStartup",
    "JoinedSquadron",
    "SquadronCreated",
    "SquadronPromotion",
    "SquadronDemotion",
)

_LEFT_EVENTS = ("LeftSquadron", "KickedFromSquadron", "DisbandedSquadron")

WATCHED = _NAME_EVENTS + _SQUADRON_EVENTS + _LEFT_EVENTS


class Identity:
    """What the session has revealed, and what has already been accepted."""

    def __init__(self):
        self._fid = ""
        self._name = ""
        self._squadron = _UNSET
        self._sent: Optional[dict] = None

    def forget(self) -> None:
        """
        A new token is a new profile as far as the site is concerned.

        Clearing what was accepted means the next watched event re-sends the
        handshake, rather than the member pasting a working token and staying
        unverified until they next start the game.
        """
        self._sent = None

    def accept(self, payload: dict) -> None:
        """Called once the site has recorded a payload, so it is not repeated."""
        self._sent = payload

    def observe(self, entry: dict, state: Optional[dict] = None) -> Optional[dict]:
        """
        Folds one journal entry in. Returns a payload worth sending, or None.

        Only the watched events can change anything, so an ordinary session's
        thousands of journal lines cost one dictionary lookup each.
        """
        event = entry.get("event")
        if event not in WATCHED:
            return None

        if event in _NAME_EVENTS:
            # `state` is EDMC's own tracking, and it has the FID even when the
            # entry does not. Preferred second, because the entry in hand is
            # about this commander for certain.
            fid = str(entry.get("FID") or (state or {}).get("FID") or "").strip()
            name = str(entry.get("Name") or entry.get("Commander") or "").strip()
            if fid:
                self._fid = fid
            if name:
                self._name = name

        elif event in _LEFT_EVENTS:
            self._squadron = None

        else:
            squadron_name = str(entry.get("SquadronName") or "").strip()
            if squadron_name:
                self._squadron = {
                    "name": squadron_name,
                    "rank": _rank(entry),
                }

        payload = self._payload()
        if payload is None or payload == self._sent:
            return None
        return payload

    def _payload(self) -> Optional[dict]:
        if not self._fid or not self._name:
            return None

        payload = {"v": 1, "fid": self._fid, "commanderName": self._name}

        # Absent rather than null: the site reads a missing key as "no
        # observation" and leaves stored standing alone.
        if self._squadron is not _UNSET:
            payload["squadron"] = self._squadron

        return payload


def _rank(entry: dict) -> Optional[int]:
    """
    The rank number, however this event spells it.

    `SquadronStartup` says `CurrentRank`; a promotion or demotion says `NewRank`.
    Neither carries the squadron's name for that rank, so the plugin sends the
    number alone and the site leaves the name to whatever Inara found.
    """
    for key in ("CurrentRank", "NewRank"):
        value = entry.get(key)
        if isinstance(value, int):
            return value
    return None
