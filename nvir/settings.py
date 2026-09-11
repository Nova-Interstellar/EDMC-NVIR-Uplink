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
    KEY_CATEGORY,
    KEY_DEBUG_MODE,
    KEY_DEV_API_URL,
    KEY_HALL_OF_FAME,
    KEY_STEALTH,
    LEGACY_DEV_URL_KEY,
    PROFILE_PATH,
    RETIRED_KEYS,
    squadron_url,
)
from .log import logger


class Settings:
    """Reads and writes what this commander chooses to broadcast."""

    def __init__(self):
        self.api_token = tk.StringVar()
        self.stealth = tk.BooleanVar()
        self.hall_of_fame = tk.BooleanVar()
        # One toggle per channel.
        self.categories = {key: tk.BooleanVar() for key in events.CATEGORIES}

        # Development only; ignored unless DEBUG is on in config.py.
        self.debug_mode = tk.BooleanVar()
        self.dev_api_url = tk.StringVar()

        # Plain copies for the delivery thread. Tk variables may only be read
        # from the thread running the main loop, and the sender is not it.
        self.api_token_value = ""
        self.debug_mode_value = False
        self.dev_api_url_value = ""

        # Set by the plugin. Fired only when the value really changes, so
        # saving the settings page for an unrelated toggle does not clear a
        # latch that is still correct.
        self.on_token_changed = None

        self.load()

    def load(self) -> None:
        self._drop_retired_keys()

        self.api_token.set(config.get_str(KEY_API_TOKEN, default=""))
        self.stealth.set(config.get_bool(KEY_STEALTH, default=False))
        # On by default. The boards are the point of collecting this, and an
        # empty Hall of Fame teaches nobody anything — but it is one tick to
        # leave, and the profile page removes what was already sent.
        self.hall_of_fame.set(config.get_bool(KEY_HALL_OF_FAME, default=True))

        for key, var in self.categories.items():
            var.set(config.get_bool(KEY_CATEGORY.format(key), default=True))

        self.debug_mode.set(config.get_bool(KEY_DEBUG_MODE, default=False))
        self.dev_api_url.set(self._load_dev_url())

        self._snapshot()

    def save(self) -> None:
        previous = self.api_token_value

        config.set(KEY_API_TOKEN, self.api_token.get().strip())
        config.set(KEY_STEALTH, self.stealth.get())
        config.set(KEY_HALL_OF_FAME, self.hall_of_fame.get())

        for key, var in self.categories.items():
            config.set(KEY_CATEGORY.format(key), var.get())

        config.set(KEY_DEBUG_MODE, self.debug_mode.get())
        config.set(KEY_DEV_API_URL, self.dev_api_url.get().strip())

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

    def profile_url(self) -> str:
        """Where to send someone to generate a token for *this* endpoint."""
        return self.base_url().rstrip("/") + PROFILE_PATH

    def is_stealthed(self) -> bool:
        return bool(self.stealth.get())

    def contributes_to_hall_of_fame(self) -> bool:
        """
        Whether lifetime statistics may be sent.

        Stealth wins. It says broadcast nothing, and a member who set it would
        not expect one channel to keep talking.
        """
        if self.is_stealthed():
            return False
        return bool(self.hall_of_fame.get())

    def is_category_enabled(self, category: str) -> bool:
        """Stealth mode overrides every individual choice without erasing it."""
        if self.is_stealthed():
            return False
        var = self.categories.get(category)
        return bool(var.get()) if var else False
