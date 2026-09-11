"""
Per-commander preferences, stored in EDMC's config.

Only two things are a commander's choice: the squadron token, and what they are
willing to broadcast. Endpoints are squadron infrastructure and live in
`config.py` — except the development endpoint, which only exists while DEBUG is
on and which Debug mode alone decides.
"""

import tkinter as tk

from config import config  # type: ignore

from . import events
from .config import (
    DEBUG,
    KEY_API_TOKEN,
    KEY_DEBUG_MODE,
    KEY_DEV_API_TOKEN,
    KEY_DEV_API_URL,
    KEY_STEALTH,
    LEGACY_DEV_URL_KEY,
    PROFILE_PATH,
    PROFILE_SHARING_PATH,
    RETIRED_KEYS,
    squadron_url,
)
from .log import logger


class Settings:
    """Reads and writes what this commander chooses to broadcast."""

    def __init__(self):
        self.api_token = tk.StringVar()
        self.stealth = tk.BooleanVar()

        # Development only; ignored unless DEBUG is on in config.py.
        self.debug_mode = tk.BooleanVar()
        self.dev_api_url = tk.StringVar()
        self.dev_api_token = tk.StringVar()

        # Plain copies for the delivery thread. Tk variables may only be read
        # from the thread running the main loop, and the sender is not it.
        self.api_token_value = ""
        self.debug_mode_value = False
        self.dev_api_url_value = ""
        self.dev_api_token_value = ""

        # Set by the plugin. Fired only when the value really changes, so
        # saving the settings page for an unrelated toggle does not clear a
        # latch that is still correct.
        self.on_token_changed = None

        self.load()

    def load(self) -> None:
        self._drop_retired_keys()

        self.api_token.set(config.get_str(KEY_API_TOKEN, default=""))
        self.stealth.set(config.get_bool(KEY_STEALTH, default=False))

        self.debug_mode.set(config.get_bool(KEY_DEBUG_MODE, default=False))
        self.dev_api_url.set(self._load_dev_url())
        self.dev_api_token.set(config.get_str(KEY_DEV_API_TOKEN, default=""))

        self._snapshot()

    def save(self) -> None:
        previous = self.api_token_value

        config.set(KEY_API_TOKEN, self.api_token.get().strip())
        config.set(KEY_STEALTH, self.stealth.get())

        config.set(KEY_DEBUG_MODE, self.debug_mode.get())
        config.set(KEY_DEV_API_URL, self.dev_api_url.get().strip())
        config.set(KEY_DEV_API_TOKEN, self.dev_api_token.get().strip())

        self._snapshot()
        logger.info("Preferences saved")

        if self.api_token_value != previous and self.on_token_changed is not None:
            self.on_token_changed()

    def _load_dev_url(self) -> str:
        """
        The development endpoint, carried over from the old key once.

        Someone who had already pointed this at staging should not have to
        find that URL again because the setting was reshaped underneath them.
        """
        stored = config.get_str(KEY_DEV_API_URL, default="")

        if not stored:
            legacy = config.get_str(LEGACY_DEV_URL_KEY, default="")
            if legacy:
                stored = legacy
                config.set(KEY_DEV_API_URL, legacy)
                logger.info("Carried the development endpoint over from %s", LEGACY_DEV_URL_KEY)

        if config.get_str(LEGACY_DEV_URL_KEY, default=""):
            config.delete(LEGACY_DEV_URL_KEY)

        return stored

    def _drop_retired_keys(self) -> None:
        """Clear webhook URLs and endpoints left by an earlier build."""
        for key in RETIRED_KEYS:
            if config.get_str(key, default=""):
                config.delete(key)
                logger.info("Removed retired setting %s", key)

    def _snapshot(self) -> None:
        """Refresh the plain copies the delivery thread reads."""
        self.api_token_value = self.api_token.get().strip()
        self.debug_mode_value = bool(self.debug_mode.get())
        self.dev_api_url_value = self.dev_api_url.get().strip()
        self.dev_api_token_value = self.dev_api_token.get().strip()

    def is_debug(self) -> bool:
        """
        Whether debug tooling is active.

        Two gates on purpose: DEBUG in config.py decides whether a build
        carries the tooling at all, and the preference decides whether this
        commander has switched it on. A release build ignores the preference.
        """
        return bool(DEBUG and self.debug_mode_value)

    def is_dev_endpoint(self) -> bool:
        """
        Whether events are going somewhere other than production.

        Dev mode alone decides it. The second checkbox that used to gate this
        only made it possible to have development tooling switched on while
        still posting into the live feed, which is never what anyone wanted.
        """
        return bool(self.is_debug() and self.dev_api_url_value)

    def base_url(self) -> str:
        """
        Where events go.

        Dev mode redirects everything while DEBUG is on, so a development build
        cannot accidentally post into the live feed. A release build
        (DEBUG = False) always uses the squadron endpoint, whatever is stored.

        Dev mode with no endpoint typed returns nothing at all, which the
        transport refuses. Falling back to production there would be the exact
        accident dev mode exists to prevent — someone who ticked the box has
        said they do not want the live feed, and an empty field is a setting
        half-finished rather than permission to post to the squadron.
        """
        if self.is_debug():
            return self.dev_api_url_value
        return squadron_url()

    def token_value(self) -> str:
        """
        The credential for wherever this build is pointed.

        A token belongs to one deployment's database, so a dev endpoint needs
        its own or every request answers "token not recognised" — which reads
        as a broken token rather than the wrong one.
        """
        if self.is_dev_endpoint():
            return self.dev_api_token_value
        return self.api_token_value

    def profile_url(self) -> str:
        """Where to send someone to generate a token for *this* endpoint."""
        return self.base_url().rstrip("/") + PROFILE_PATH

    def sharing_url(self) -> str:
        """The part of the profile that decides what this plugin may publish."""
        return self.base_url().rstrip("/") + PROFILE_SHARING_PATH

    def is_stealthed(self) -> bool:
        return bool(self.stealth.get())

    def contributes_to_hall_of_fame(self) -> bool:
        """
        Whether lifetime statistics may be sent.

        Stealth and nothing else, the same rule the feed categories follow.

        There used to be a checkbox here as well. It was the last per-feature
        send switch left on this machine after the broadcast choices moved, and
        it duplicated a decision the site already enforces: an opted-out member
        is refused with a terminal code and has their stored totals deleted, so
        a local switch could only ever disagree with the real one.
        """
        return not self.is_stealthed()

    def is_category_enabled(self, category: str) -> bool:
        """
        Whether this category may be sent at all.

        Only Stealth decides it here. Which categories a member wants announced
        moved to their NVIR profile, where there is room to say what each one
        covers and where changing the list never needs a plugin release.

        The site enforces that choice on arrival rather than asking the plugin
        to honour it. Two reasons: it takes effect the moment the box is
        unticked instead of at the next game session, and a plugin on someone
        else's machine can only ever be advised, never relied on.

        Stealth stays because it is the one switch that must work with the site
        unreachable, and must not be something a server can turn back on.
        """
        return not self.is_stealthed()
