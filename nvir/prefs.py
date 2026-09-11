"""
Preferences tab.

Two settings a commander actually owns: the squadron token, and what they
broadcast. Endpoints ship in `config.py` — nobody should have to paste a URL to
use this. The Development section exists only in a build with `DEBUG` on.

Built against EDMC 6.x widgets: there is no `nb.Entry` any more (it is
`nb.EntryMenu`), and `plugin_prefs` is isinstance-checked, so every frame
returned from here — including an error frame — must be an `nb.Frame`.
"""

import tkinter as tk
import webbrowser
from tkinter import font as tkfont
from tkinter import ttk

import myNotebook as nb  # type: ignore

from . import events, version
from .config import DEBUG, GITHUB_URL, PLUGIN_TITLE, PLUGIN_VERSION
from .log import logger

PAD = {"padx": 10, "pady": 3}
LINK_COLOR = "#3b82f6"
ERROR_COLOR = "#d9534f"


class PreferencesUI:
    """The plugin's page in EDMC's settings dialog."""

    def __init__(self, settings, checker=None, error=None):
        self._settings = settings
        self._checker = checker
        self._error = error
        self._category_boxes = {}
        self._bold = None
        self._dev_url_entry = None
        self._version_link = None

    def build(self, parent) -> nb.Frame:
        frame = nb.Frame(parent)
        frame.columnconfigure(1, weight=1)

        # nb.Frame grids its own spacer into row 0, so content starts at 1.
        row = 1
        row = self._title_row(frame, row)
        row = self._rule(frame, row)

        nb.Label(frame, text="Squadron Member Token").grid(row=row, column=0, sticky=tk.W, **PAD)
        nb.EntryMenu(
            frame, textvariable=self._settings.api_token, show="\N{BULLET}"
        ).grid(row=row, column=1, sticky=tk.EW, **PAD)
        row += 1

        # The same failure the main window is showing, repeated where the fix
        # is. Someone who reads "token not recognised" on the status row has to
        # come here anyway; making them remember it on the way is pointless.
        if self._error:
            nb.Label(
                frame,
                text=self._error,
                foreground=ERROR_COLOR,
                wraplength=380,
                justify=tk.LEFT,
            ).grid(row=row, column=0, columnspan=2, sticky=tk.W, **PAD)
            row += 1

        # Points at whichever site the plugin is currently sending to. A token
        # belongs to one deployment's database, so linking to production while
        # a development build talks to staging would hand out a token that
        # cannot work.
        profile_link = nb.Label(
            frame,
            text="Generate a token on your NVIR profile",
            foreground=LINK_COLOR,
            cursor="hand2",
        )
        profile_link.grid(row=row, column=0, columnspan=2, sticky=tk.W, **PAD)
        profile_link.bind("<Button-1>", self._open_profile)
        row += 1

        nb.Checkbutton(
            frame,
            text="Stealth Mode \N{EM DASH} broadcast nothing",
            variable=self._settings.stealth,
            command=self._sync_enabled,
        ).grid(row=row, column=0, columnspan=2, sticky=tk.W, **PAD)
        row += 1

        nb.Checkbutton(
            frame,
            text="Contribute to the NVIR Hall of Fame",
            variable=self._settings.hall_of_fame,
        ).grid(row=row, column=0, columnspan=2, sticky=tk.W, **PAD)
        row += 1

        # Said here rather than left to be discovered. This one is on unless you
        # turn it off, and what NVIR already holds is removed from the profile
        # page, not from here.
        nb.Label(
            frame,
            text=(
                "Sends your in-game statistics totals for the squadron leaderboards. "
                "Manage or delete what NVIR holds on your profile."
            ),
            wraplength=420,
            justify=tk.LEFT,
        ).grid(row=row, column=0, columnspan=2, sticky=tk.W, **PAD)
        row += 1

        row = self._rule(frame, row)
        row = self._broadcast_section(frame, row)

        if DEBUG:
            row = self._rule(frame, row)
            row = self._debug_section(frame, row)

        self._sync_enabled()
        return frame

    # --- sections -----------------------------------------------------------

    def _title_row(self, frame, row: int) -> int:
        nb.Label(
            frame, text="{0} v{1}".format(PLUGIN_TITLE, PLUGIN_VERSION)
        ).grid(row=row, column=0, sticky=tk.W, **PAD)

        # Always a link to the repository, whatever the check says.
        self._version_link = nb.Label(
            frame, text="", foreground=LINK_COLOR, cursor="hand2"
        )
        self._version_link.grid(row=row, column=1, sticky=tk.E, **PAD)
        self._version_link.bind("<Button-1>", self._open_repository)

        self._render_version(
            self._checker.state if self._checker else version.VersionState(
                version.UNAVAILABLE
            )
        )
        if self._checker is not None:
            self._checker.subscribe(self._on_version)

        return row + 1

    def _broadcast_section(self, frame, row: int) -> int:
        """
        A titled block, then one checkbox per channel, two to a row.

        Each channel is a single toggle now: CQC rank-ups ride along with
        combat, and there is nothing else beneath any of them. Adding a channel
        is one entry in events.CATEGORIES, not a layout change.
        """
        nb.Label(frame, text="Broadcast", font=self._heading_font()).grid(
            row=row, column=0, columnspan=2, sticky=tk.W, **PAD
        )
        row += 1

        grid = nb.Frame(frame)
        grid.grid(row=row, column=0, columnspan=2, sticky=tk.EW, padx=26, pady=(2, 4))
        grid.columnconfigure(0, weight=1, uniform="broadcast")
        grid.columnconfigure(1, weight=1, uniform="broadcast")

        for index, category in enumerate(events.CATEGORY_ORDER):
            box = nb.Checkbutton(
                grid,
                text=events.label_of(category),
                variable=self._settings.categories[category],
            )
            box.grid(
                row=index // 2,
                column=index % 2,
                sticky=tk.W,
                padx=(0, 12),
                pady=1,
            )
            self._category_boxes[category] = box

        return row + 1

    def _debug_section(self, frame, row: int) -> int:
        """
        One row: the switch, and where it sends.

        No heading and no second checkbox. Dev mode already means "not
        production", and the endpoint is the only thing left to say about it —
        a section title above a single control is furniture.
        """
        nb.Checkbutton(
            frame,
            text="Enable Dev Mode",
            variable=self._settings.debug_mode,
            command=self._sync_enabled,
        ).grid(row=row, column=0, sticky=tk.W, **PAD)

        self._dev_url_entry = nb.EntryMenu(
            frame, textvariable=self._settings.dev_api_url
        )
        self._dev_url_entry.grid(row=row, column=1, sticky=tk.EW, **PAD)

        return row + 1

    def _heading_font(self):
        """Bold copy of the default label font, resolved once."""
        if self._bold is None:
            base = tkfont.nametofont("TkDefaultFont")
            self._bold = tkfont.Font(font=base)
            self._bold.configure(weight="bold")
        return self._bold

    @staticmethod
    def _rule(frame, row: int) -> int:
        ttk.Separator(frame, orient=tk.HORIZONTAL).grid(
            row=row, column=0, columnspan=2, sticky=tk.EW, padx=10, pady=8
        )
        return row + 1

    # --- version ------------------------------------------------------------

    def _open_profile(self, _event=None) -> None:
        webbrowser.open(self._settings.profile_url())

    def _open_repository(self, _event=None) -> None:
        webbrowser.open(GITHUB_URL)

    def _on_version(self, state) -> None:
        # May arrive on the checking thread; hop back before touching a widget.
        if self._version_link is None:
            return
        try:
            self._version_link.after(0, lambda: self._render_version(state))
        except tk.TclError:  # settings closed while the check was in flight
            pass

    def _render_version(self, state) -> None:
        if self._version_link is None:
            return
        try:
            self._version_link.configure(text=state.label())
        except tk.TclError:
            pass

    # --- enablement ---------------------------------------------------------

    def _sync_enabled(self) -> None:
        """
        Stealth mode locks every broadcast toggle without clearing it, and the
        endpoint field appears only once dev mode is on — hidden rather than
        greyed out, since an empty disabled box invites the question of what it
        would have been for.
        """
        state = tk.DISABLED if self._settings.is_stealthed() else tk.NORMAL
        for box in self._category_boxes.values():
            self._set_state(box, state)

        if not DEBUG or self._dev_url_entry is None:
            return

        try:
            if self._settings.debug_mode.get():
                self._dev_url_entry.grid()
            else:
                self._dev_url_entry.grid_remove()
        except tk.TclError:
            pass



    @staticmethod
    def _set_state(widget, state) -> None:
        try:
            widget.configure(state=state)
        except tk.TclError:  # widget already destroyed
            pass


def error_frame(parent, message: str) -> nb.Frame:
    """A prefs page that reports its own failure instead of vanishing."""
    logger.error("Preferences UI failed: %s", message)
    frame = nb.Frame(parent)
    frame.columnconfigure(0, weight=1)
    nb.Label(frame, text="NVIR could not build its settings page.").grid(
        row=1, column=0, sticky=tk.W, **PAD
    )
    nb.Label(frame, text=str(message)).grid(row=2, column=0, sticky=tk.W, **PAD)
    return frame
