"""
Delivery queue.

EDMC calls journal_entry on its main thread, so nothing here may block: a
single rate-limited webhook post would otherwise freeze the whole application.
Events are queued and a daemon thread does the talking.
"""

import queue
import threading
from typing import Callable, Optional

from .config import MAX_ATTEMPTS
from .log import logger
from .standing import Standing
from .transport import Delivery

# Pushed onto the queue to wake the worker for shutdown.
_SHUTDOWN = object()


class Sender:
    """Queues payloads and delivers them on a background thread."""

    def __init__(self, transport, standing=None):
        self._transport = transport
        self._standing = standing or Standing()
        self._queue: queue.Queue = queue.Queue()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        # For the diagnostics report. Written on the delivery thread and read
        # on the main one, which is safe for a plain int and not worth a lock
        # for a number nobody acts on.
        self._delivered = 0
        self._refused = 0

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name="NVIR-sender", daemon=True
        )
        self._thread.start()
        logger.info("Delivery thread started")

    def stop(self, timeout: float = 5.0) -> None:
        if self._thread is None:
            return
        self._stop.set()
        self._queue.put(_SHUTDOWN)
        self._thread.join(timeout=timeout)
        self._thread = None
        self._transport.close()
        logger.info("Delivery thread stopped")

    @property
    def transport(self):
        return self._transport

    @property
    def standing(self) -> Standing:
        return self._standing

    def _drain(self) -> None:
        """
        Throws away everything still queued.

        Called when the site has refused the credential outright. Holding the
        backlog would mean flushing it the moment a new token is pasted, which
        posts a burst of stale events — and, after a revoke, delivers data the
        squadron had decided to stop receiving.
        """
        dropped = 0
        while True:
            try:
                item = self._queue.get_nowait()
            except queue.Empty:
                break
            self._queue.task_done()
            if item is not _SHUTDOWN:
                dropped += 1

        if dropped:
            logger.warning("Dropped %d queued event(s): uplink is latched", dropped)

    def pending(self) -> int:
        return self._queue.qsize()

    def submit(
        self,
        payload: dict,
        on_result: Optional[Callable[[Delivery], None]] = None,
        kind: str = "event",
    ) -> None:
        """
        Queue a payload for delivery.

        `kind` picks the endpoint: "event" for the feed, "identity" for the
        handshake, "statistics" for the Hall of Fame. Same queue and same
        credential, because ordering between them matters — a handshake that
        overtook a rename would record the old name.

        `on_result` is invoked on the worker thread, so a Tk caller must
        marshal back with `widget.after(...)` before touching any widget.
        """
        # Nothing is queued while latched. The worker would refuse it anyway;
        # this keeps a long session from growing a backlog it will only drop.
        if self._standing.is_latched():
            logger.debug("Not queueing %s: uplink is latched", payload.get("event", "?"))
            return

        self._queue.put((payload, on_result, kind))

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                item = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue

            if item is _SHUTDOWN:
                break

            payload, on_result, kind = item
            try:
                result = self._deliver(payload, kind)
            except Exception as err:  # never let the worker die on one event
                logger.exception("Delivery raised")
                result = Delivery(False, detail=str(err))
            finally:
                self._queue.task_done()

            # Recorded here rather than in the UI callback, so the next item in
            # the queue already knows — a revoked token stops the whole backlog
            # rather than each event discovering it one at a time.
            if self._standing.record(result):
                logger.error("Uplink latched (%s): %s", result.code, result.detail)
                self._drain()

            if on_result is not None:
                try:
                    on_result(result)
                except Exception:
                    logger.exception("Delivery callback raised")

    def _deliver(self, payload: dict, kind: str = "event") -> Delivery:
        event_name = payload.get("event", kind)
        result = Delivery(False, detail="Not attempted")

        # Refused before it is sent. The site has already said this credential
        # will not work, so asking again on every journal entry only fills the
        # log with the same rejection.
        if self._standing.is_latched():
            return Delivery(
                False,
                detail=self._standing.detail or "Uplink stopped",
                code=self._standing.code,
                terminal=True,
            )

        post = {
            "identity": self._transport.send_identity,
            "statistics": self._transport.send_statistics,
        }.get(kind, self._transport.send)

        for attempt in range(1, MAX_ATTEMPTS + 1):
            result = post(payload)

            if result.ok:
                self._delivered += 1
                logger.info("Sent %s (attempt %d)", event_name, attempt)
                return result

            if not result.retryable or attempt == MAX_ATTEMPTS:
                break

            logger.warning(
                "Retrying %s in %.1fs (%s)", event_name, result.retry_after, result.detail
            )
            # Waiting on the stop event keeps shutdown responsive during a
            # rate-limit back-off.
            if self._stop.wait(result.retry_after):
                return result

        # `attempt`, not MAX_ATTEMPTS: a refusal that is not retryable gives up
        # after one try, and a log claiming three would send whoever reads it
        # hunting for two requests that never happened.
        self._refused += 1
        logger.error(
            "Dropped %s after %d attempt(s): %s", event_name, attempt, result.detail
        )
        return result

    def summary(self) -> str:
        """
        What the wire has actually carried, for the diagnostics report.

        Worth its own line because zero is the interesting number: a plugin
        that has queued things and delivered none is a different problem from
        one that has never had anything to queue, and no other line separates
        them.
        """
        if not self._delivered and not self._refused:
            return "nothing sent yet"
        return "{0} delivered, {1} refused".format(self._delivered, self._refused)
