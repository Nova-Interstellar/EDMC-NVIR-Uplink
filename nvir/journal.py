"""
Journal handling: decide whether an entry is worth broadcasting, then queue it.

Runs on EDMC's main thread, so it does no network work of its own.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from . import events, payload
from .identity import Identity
from .statistics import Statistics
from .config import REPLAY_GRACE_SECONDS
from .log import logger


class Journal:
    """Filters journal entries down to the ones the registry declares."""

    def __init__(self, settings, sender, on_delivery=None):
        self._settings = settings
        self._sender = sender
        self._on_delivery = on_delivery
        # EDMC replays the current journal file when it loads, so anything
        # stamped before the plugin started is history, not news.
        self._started_at = datetime.now(timezone.utc) - timedelta(
            seconds=REPLAY_GRACE_SECONDS
        )
        self._owned_carriers = set()
        self._identity = Identity()
        self._statistics = Statistics()
        self._last_result = ""
        self._seen = 0
        self._first_event = ""

    @property
    def last_result(self) -> str:
        return self._last_result

    def summary(self) -> list:
        """
        What this session has learned, for the diagnostics report.

        These two lines answer the question a broken uplink actually poses:
        whether the plugin has anything to send, or whether it has been sending
        and being refused. Nothing else distinguishes them from the outside.
        """
        return [
            ("Journal", self._journal_summary()),
            ("Handshake", self._identity.summary()),
            ("Statistics", self._statistics.summary()),
            ("Carriers owned", str(len(self._owned_carriers))),
        ]

    def _journal_summary(self) -> str:
        """
        Whether EDMC is talking to us at all, which nothing else establishes.

        Its own Cmdr and System fields come from EDMC's monitor rather than
        this hook, so a main window full of the right commander says nothing
        about whether a single entry reached the plugin.
        """
        if not self._seen:
            return "NOTHING RECEIVED — EDMC has sent this plugin no journal entries"
        return "{0} {1}, first was {2}".format(
            self._seen, "entry" if self._seen == 1 else "entries", self._first_event
        )

    def resend_state(self) -> None:
        """
        Offers everything this session knows, as if it had never been sent.

        Called when the token changes. Clearing what was accepted is not enough
        on its own: both `Identity` and `Statistics` can only produce a payload
        while the journal entry that carries it is in hand, and those entries
        arrive at login. Pasting a token afterwards — which is what everybody
        does, since the token is what the plugin was installed for — would leave
        the member unverified and off the boards until the next game session,
        with the panel reporting Online throughout.

        Sending immediately costs at most two requests the site would have
        received anyway.
        """
        self._identity.forget()
        self._statistics.forget()

        identity = self._identity.pending()
        if identity is not None:
            logger.info("Token changed: re-sending the handshake")
            self._send_identity(identity)
        else:
            logger.info("Token changed: no handshake to re-send yet")

        # Gated exactly as `_contribute` is, or a stealthed member would
        # contribute by pasting a token — the one act that guarantees they are
        # looking at the settings page and believe nothing is being sent.
        if not self._settings.contributes_to_hall_of_fame():
            logger.info("Token changed: statistics held back (Stealth Mode)")
            return

        statistics = self._statistics.pending()
        if statistics is not None:
            logger.info("Token changed: re-sending statistics")
            self._send_statistics(statistics)

    def on_entry(
        self,
        cmdr: str,
        is_beta: bool,
        system: Optional[str],
        station: Optional[str],
        entry: dict,
        state: dict,
    ) -> None:
        if is_beta:
            return

        event_name = entry.get("event")
        if not event_name:
            return

        # Once, so a report says whether EDMC is talking to us at all. Every
        # other explanation for a silent uplink assumes journal entries are
        # arriving, and that is the assumption nothing else tests: EDMC's own
        # Cmdr and System fields come from its monitor, not from this hook, so
        # a populated main window proves nothing about the plugin.
        self._seen += 1
        if self._seen == 1:
            self._first_event = event_name
            logger.info(
                "First journal entry: %s (commander %s)", event_name, cmdr or "unknown"
            )

        # Learn which carriers belong to this commander before the replay
        # guard runs: CarrierStats arrives during the login replay, and it is
        # what lets us tell an owned carrier's jump from one we are riding.
        if event_name in events.CARRIER_OWNERSHIP_EVENTS:
            carrier_id = entry.get("CarrierID")
            if carrier_id:
                self._owned_carriers.add(int(carrier_id))

        # Also before the guard, and for the same reason: Commander and LoadGame
        # arrive in the login replay, and they are the only events that carry an
        # FID. Dropping them as history would leave every member unverified
        # whenever EDMC started after the game.
        self._handshake(entry, state)
        self._contribute(entry)

        if self._is_replay(entry):
            return

        spec = events.spec_for(event_name)
        if spec is None:
            return

        # CarrierJump fires for everyone docked aboard, so without this a
        # passenger would announce somebody else's carrier as their own.
        if event_name == "CarrierJump":
            market_id = entry.get("MarketID")
            if not market_id or int(market_id) not in self._owned_carriers:
                logger.debug("Ignoring CarrierJump for a carrier we do not own")
                return

        # Nothing this event could reach is switched on, so do not build it.
        if not any(
            self._settings.is_category_enabled(category)
            for category in spec.categories()
        ):
            return

        for built in payload.build(cmdr, event_name, entry, system, station):
            # Re-checked per payload: one Promotion can post the rank-up a
            # commander shares and drop another they do not.
            if not self._settings.is_category_enabled(built["category"]):
                continue
            logger.info("Queued %s (%s) for %s", event_name, built["category"], cmdr)
            self._sender.submit(built, on_result=self._record)

    def _handshake(self, entry: dict, state: dict) -> None:
        """
        Sends the identity payload, if this entry changed what we know.

        Not gated on any category: the handshake is who the commander is, not
        something they broadcast, and a member who shares nothing still wants
        their profile to say their own name.
        """
        proposed = self._identity.observe(entry, state)
        if proposed is None:
            return

        logger.info(
            "Handshake from %s: commander %s",
            entry.get("event"),
            proposed.get("commanderName"),
        )
        self._send_identity(proposed)

    def _send_identity(self, proposed: dict) -> None:
        logger.info("Queued identity for %s", proposed.get("commanderName"))
        self._sender.submit(
            proposed,
            on_result=lambda result, sent=proposed: self._identity_result(sent, result),
            kind="identity",
        )

    def _contribute(self, entry: dict) -> None:
        """
        Sends lifetime statistics for the Hall of Fame, when they have moved.

        Ahead of the replay guard like the handshake, and for the same reason:
        `Statistics` arrives in EDMC's login replay, so treating it as history
        would mean a member only ever contributed when they alt-tabbed mid-game.

        Gated on its own setting rather than on any broadcast category. This is
        not something the commander did, it is what they have done, and the
        squadron boards are a different question from the feed.
        """
        if not self._settings.contributes_to_hall_of_fame():
            return

        proposed = self._statistics.observe(entry)
        if proposed is None:
            return

        self._send_statistics(proposed)

    def _send_statistics(self, proposed: dict) -> None:
        logger.info("Queued statistics (%d sections)", len(proposed["statistics"]))
        self._sender.submit(
            proposed,
            on_result=lambda result, sent=proposed: self._statistics_result(sent, result),
            kind="statistics",
        )

    def _statistics_result(self, sent: dict, result) -> None:
        """
        Files the submission's outcome. Runs on the delivery thread.

        Quiet on success, like the handshake: nobody asked for this to happen
        just now, and saying so would bury the result of the event they were
        actually watching.

        A refusal stops the asking. `hall_of_fame_off` means the member deleted
        their record from their profile, and repeating the request at every
        login would be arguing with them.
        """
        if result.ok:
            self._statistics.accept(sent)
            return

        if getattr(result, "code", "") == "hall_of_fame_off":
            self._statistics.refuse()

        self._record(result)

    def _identity_result(self, sent: dict, result) -> None:
        """
        Files the handshake's outcome. Runs on the delivery thread.

        A success is deliberately quiet — it is not something the member
        did, and overwriting the panel with it would bury the result of the event
        they were actually watching. A failure is not quiet: an FID another
        profile has claimed needs an officer, and nobody would ever find that in
        a log.
        """
        if result.ok:
            self._identity.accept(sent)
            return

        self._record(result)

    def _record(self, result) -> None:
        self._last_result = result.detail

        # Live events used to fail silently: the detail was stored here and
        # nothing ever read it, so a revoked token looked exactly like a quiet
        # evening.
        if self._on_delivery is not None:
            self._on_delivery(result)

    def _is_replay(self, entry: dict) -> bool:
        stamped = self._parse_timestamp(entry.get("timestamp"))
        if stamped is None:
            # An entry we cannot date is treated as live; the game writes a
            # timestamp on every line, so this should not happen.
            return False
        return stamped < self._started_at

    @staticmethod
    def _parse_timestamp(value) -> Optional[datetime]:
        if not value:
            return None
        try:
            return datetime.strptime(str(value), "%Y-%m-%dT%H:%M:%SZ").replace(
                tzinfo=timezone.utc
            )
        except ValueError:
            return None
