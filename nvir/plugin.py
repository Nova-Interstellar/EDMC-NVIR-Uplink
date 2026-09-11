"""Wires the pieces together and holds the plugin's live state."""

from datetime import datetime
from typing import Optional

from . import debug_panel, prefs, standing, transport, version
from .config import PLUGIN_NAME, PLUGIN_VERSION
from .journal import Journal
from .log import logger
from .sender import Sender
from .settings import Settings


class Plugin:
    """One instance per EDMC run."""

    def __init__(self):
        # The last delivery failure, or None while sending is healthy. Held here
        # rather than in the panel because the settings page needs it too, and
        # that page is rebuilt from scratch every time it opens.
        self.last_error: Optional[str] = None
        self.standing = standing.Standing()
        self.settings: Optional[Settings] = None
        self.sender: Optional[Sender] = None
        self.journal: Optional[Journal] = None
        self.panel: Optional[debug_panel.AppPanel] = None
        self.checker = version.Checker()
        self.cmdr = ""
        # So the report can say whether the log covers the whole session.
        self.started_at = datetime.now()

    def start(self) -> str:
        self.settings = Settings()
        self.settings.on_token_changed = self._on_token_changed
        self.sender = Sender(transport.build(self.settings), self.standing)
        self.sender.start()
        self.journal = Journal(self.settings, self.sender, self.note_delivery)
        self.panel = debug_panel.AppPanel(self)
        self.checker.start()

        logger.info("%s %s started", PLUGIN_NAME, PLUGIN_VERSION)
        return PLUGIN_NAME

    def stop(self) -> None:
        if self.sender is not None:
            self.sender.stop()
            self.sender = None
        logger.info("%s stopped", PLUGIN_NAME)

    def _on_token_changed(self) -> None:
        """
        A new token deserves a try.

        The latch exists to stop hammering a credential the site has rejected;
        the moment the member replaces it, that reasoning no longer applies and
        holding the stop would look like the plugin ignoring them.
        """
        self.standing.clear()
        self.last_error = None

        if self.panel is not None:
            self.panel.clear_error()

        logger.info("Token changed: uplink resumed")

        # The site keys identity off the token's profile, so a new token means
        # the handshake has to happen again — and it has to happen now. The
        # events carrying it fired at login, so waiting for the next one means
        # waiting for the next game session.
        #
        # After clear_error, because these are sends and one of them failing
        # should leave its own message on the panel rather than be wiped by the
        # reset that let it happen.
        if self.journal is not None:
            self.journal.resend_state()

    def note_delivery(self, result) -> None:
        """
        Records what the last send did.

        Called on the delivery thread, so nothing here may touch a widget —
        `AppPanel.report` marshals back to the main loop itself.

        A success clears the error. Anything else keeps the site's own words:
        the API explains what is wrong far better than "delivery failed" can,
        and it is the member who has to act on it.
        """
        # The site's full sentence, for the settings page. The panel shortens
        # it for itself — there is room for an explanation beside the field
        # that fixes it, and none at all in the main window.
        self.last_error = None if result.ok else (result.detail or "Delivery failed")

        if self.panel is not None:
            self.panel.report(result)

    def app_widgets(self, parent):
        return self.panel.build(parent) if self.panel else None

    def prefs_widget(self, parent):
        try:
            return prefs.PreferencesUI(
                self.settings, self.checker, self.last_error, controller=self
            ).build(parent)
        except Exception as err:
            logger.exception("Building the preferences page failed")
            return prefs.error_frame(parent, err)

    def save_prefs(self) -> None:
        if self.settings is None:
            return
        self.settings.save()
        if self.panel is not None:
            # Debug mode is a preference now, so the button appears and
            # disappears with it rather than waiting for a restart.
            self.panel.sync()

    def on_journal(self, cmdr, is_beta, system, station, entry, state) -> None:
        if cmdr:
            self.cmdr = cmdr
        if self.journal is not None:
            self.journal.on_entry(cmdr, is_beta, system, station, entry, state)
