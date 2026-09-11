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

# Pilot ranks. `Rank` carries the tier index per career, `Progress` the percent
# into the next one; both fire in the login sequence and again on a rank-up.
#
# The percentage is the only reason this is here. Inara already publishes the
# rank names, but nothing outside the journal knows a commander is 89% of the
# way to Elite -- and that is the number /tools/rank-progress needs to say what
# is left to earn.
_RANK_EVENTS = ("Rank", "Progress")

# The careers the journal names. Fixed rather than "whatever keys turned up", so
# a future addition to the event cannot quietly widen what we transmit.
RANK_CAREERS = (
    "Combat",
    "Trade",
    "Explore",
    "Soldier",
    "Exobiologist",
    "Empire",
    "Federation",
    "CQC",
)

WATCHED = _NAME_EVENTS + _SQUADRON_EVENTS + _LEFT_EVENTS + _RANK_EVENTS


class Identity:
    """What the session has revealed, and what has already been accepted."""

    def __init__(self):
        self._fid = ""
        self._name = ""
        self._squadron = _UNSET
        # career -> {"rank": int} and/or {"progress": int}, merged as the two
        # events arrive. They are separate journal lines, so neither is complete
        # on its own and the payload waits for nothing -- a rank with no
        # percentage yet is still worth sending.
        self._ranks: dict = {}
        self._sent: Optional[dict] = None

    def forget(self) -> None:
        """
        A new token is a new profile as far as the site is concerned.

        Clearing what was accepted is only half of it — see `pending`. The
        watched events all fire at login and nowhere else, so on its own this
        would leave the member waiting for a game restart.
        """
        self._sent = None

    def summary(self) -> str:
        """
        One line for the diagnostics report.

        The FID is reduced to whether it exists. It is not a secret — the game
        shows the commander name to anyone in the same instance — but a report
        gets pasted into Discord, and whether the handshake has the id is the
        only part anybody debugging needs.
        """
        if not self._fid and not self._name:
            return "not observed yet (no Commander or LoadGame this session)"

        return "{0}, FID {1}, {2} rank(s), {3}".format(
            self._name or "(no name)",
            "known" if self._fid else "MISSING",
            len(self._ranks) or "no",
            "accepted by the site" if self._sent else "not yet accepted",
        )

    def pending(self) -> Optional[dict]:
        """
        What this session knows, if the site has not already taken it.

        `observe` can only answer while a watched entry is in hand, and every
        one of them fires at login: `Commander` and `LoadGame` once, the
        squadron events a handful of times a year. So a member who pastes their
        token mid-session has already missed the only chance to be seen — the
        handshake would wait for the next game start, with the plugin reporting
        Online the whole time.

        This is the same question asked without an entry, so a token change can
        offer what is already known immediately.
        """
        payload = self._payload()
        if payload is None or payload == self._sent:
            return None
        return payload

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

        elif event in _RANK_EVENTS:
            self._fold_ranks(event, entry)

        elif event in _LEFT_EVENTS:
            self._squadron = None

        else:
            squadron_name = str(entry.get("SquadronName") or "").strip()
            if squadron_name:
                self._squadron = {
                    "name": squadron_name,
                    "rank": _rank(entry),
                }

        return self.pending()

    def _payload(self) -> Optional[dict]:
        if not self._fid or not self._name:
            return None

        payload = {"v": 1, "fid": self._fid, "commanderName": self._name}

        # Absent rather than null: the site reads a missing key as "no
        # observation" and leaves stored standing alone.
        if self._squadron is not _UNSET:
            payload["squadron"] = self._squadron

        # Same rule. An empty dict would tell the site the commander has no
        # ranks, which is not a thing the game can report.
        if self._ranks:
            payload["ranks"] = self._ranks

        return payload

    def _fold_ranks(self, event: str, entry: dict) -> None:
        """
        Merges a `Rank` or `Progress` entry into what is known per career.

        They are two journal lines carrying the same keys with different
        meanings — the tier index and the percent into the next one — so each
        contributes one field and neither waits for the other. A rank with no
        percentage yet is still worth sending; the site treats a missing
        `progress` as unknown rather than zero, which is a different claim.

        Anything not an integer is dropped rather than passed on. The site
        validates too, but sending a value we already know is wrong just moves
        the refusal further from the thing that produced it.
        """
        field = "rank" if event == "Rank" else "progress"

        for career in RANK_CAREERS:
            value = entry.get(career)
            if not isinstance(value, int) or isinstance(value, bool):
                continue
            if value < 0:
                continue
            self._ranks.setdefault(career, {})[field] = value


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
