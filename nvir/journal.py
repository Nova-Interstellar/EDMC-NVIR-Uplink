"""
Journal handling: decide whether an entry is worth broadcasting, then queue it.

Runs on EDMC's main thread, so it does no network work of its own.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from . import events, payload
from .identity import Identity
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
        self._last_result = ""

    @property
    def last_result(self) -> str:
        return self._last_result

    def forget_identity(self) -> None:
        """A new token deserves a fresh handshake, not a session's worth of wait."""
        self._identity.forget()

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

        logger.info("Queued identity for %s", proposed.get("commanderName"))
        self._sender.submit(
            proposed,
            on_result=lambda result, sent=proposed: self._identity_result(sent, result),
            kind="identity",
        )

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
