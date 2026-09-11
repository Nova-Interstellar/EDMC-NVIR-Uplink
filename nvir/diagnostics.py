"""
The report a member sends us when something is not working.

Asking somebody to find EDMC's log folder, pick the right file out of it and
then locate our lines among every other plugin's is asking for a report we will
not get. This assembles the same thing in one button: what the plugin is
configured to do, what it has learned this session, and everything it has
logged, with the secrets masked so it can be pasted into Discord as it stands.

Nothing here reads a file. The log lines come from the ring buffer in `log.py`,
so what a member sends is exactly what the plugin said, in order, this session.
"""

import tkinter as tk
from datetime import datetime
from tkinter import ttk

from .config import DEBUG, PLUGIN_TITLE, PLUGIN_VERSION
from .log import PLUGIN_DIR, logger, mask, recent


INDENT = "  "


def _environment(controller) -> list:
    """
    How this plugin is configured. Nested where one setting owns another.

    A row of `(label, value, depth)`. Depth is what puts the dev endpoint and
    dev token under Dev Mode rather than beside it: they are meaningless when it
    is off, and a flat list invites reading them as three separate problems.
    """
    settings = controller.settings

    panel = getattr(controller, "panel", None)
    status = panel.status_text() if panel is not None else "(no panel)"

    rows = [
        ("Status", status, 0),
        ("Endpoint", settings.base_url() or "(nowhere — Dev Mode with no endpoint)", 0),
        ("Token", mask(settings.api_token_value), 0),
        ("Stealth Mode", "ON — nothing is sent" if settings.is_stealthed() else "off", 0),
    ]

    # Only in a build that carries the tooling. A release build ignores these
    # outright, so listing them would invite a member to change something that
    # cannot matter.
    if DEBUG:
        on = bool(settings.debug_mode_value)
        rows.append(("Dev Mode", "on" if on else "off", 0))
        if on:
            rows += [
                ("Dev endpoint", settings.dev_api_url_value or "(not set)", 1),
                ("Dev token", mask(settings.dev_api_token_value), 1),
            ]

    rows += [
        ("Plugin folder", PLUGIN_DIR, 0),
        ("Running on", _host(), 0),
    ]
    return rows


def _session(controller) -> list:
    """What the game and the wire have said since EDMC started."""
    rows = []

    journal = getattr(controller, "journal", None)
    if journal is None:
        rows.append(("Journal", "not started", 0))
    else:
        rows += [(label, value, 0) for label, value in journal.summary()]

    sender = getattr(controller, "sender", None)
    rows.append(("Deliveries", sender.summary() if sender else "not started", 0))
    return rows


def _host() -> str:
    """EDMC and Python, best effort — neither is worth failing a report over."""
    import platform

    try:
        from config import appversion  # type: ignore

        edmc = "EDMC {0}".format(appversion())
    except Exception:
        # Not every EDMC exposes it, and a report is worth more than a version.
        edmc = "EDMC (version unknown)"

    return "{0}, Python {1}, {2}".format(
        edmc, platform.python_version(), platform.system()
    )


def _block(title: str, rows: list) -> list:
    """One titled section, its labels aligned down the whole block."""
    if not rows:
        return []

    # Aligned including the indent, so a nested label's value still lines up
    # with its siblings above rather than starting a second column.
    width = max(len(INDENT * depth + label) for label, _, depth in rows)

    lines = ["--- {0} ---".format(title), ""]
    lines += [
        "{0}{1}  {2}".format(INDENT, (INDENT * depth + label).ljust(width), value)
        for label, value, depth in rows
    ]
    lines.append("")
    return lines


def _prose(title: str, text: str) -> list:
    """A section that is one sentence rather than a table."""
    return ["--- {0} ---".format(title), "", INDENT + text, ""]


def report(controller) -> str:
    """The whole thing as one string, ready to paste."""
    started = getattr(controller, "started_at", None)
    taken = datetime.now()

    header = "Taken {0} local".format(taken.strftime("%Y-%m-%d %H:%M:%S"))
    if started is not None:
        minutes = max(int((taken - started).total_seconds() // 60), 0)
        # So a reader knows whether the log covers the session or only the tail
        # of it — 500 lines is a lot for an evening and nothing for a weekend.
        header += ", {0} minutes after the plugin loaded".format(minutes)

    lines = ["{0} v{1} — diagnostics".format(PLUGIN_TITLE, PLUGIN_VERSION), header, ""]
    lines += _block("Environment", _environment(controller))
    lines += _block("Session", _session(controller))
    lines += _prose("Last error", controller.last_error or "none")

    entries = recent()
    lines += ["--- Log ({0} lines) ---".format(len(entries)), ""]
    lines += [INDENT + entry for entry in (entries or ["(nothing logged yet)"])]

    return "\n".join(lines)


class LogWindow:
    """A read-only view of the report, with one button that copies it."""

    def __init__(self, parent, controller):
        self._controller = controller
        self._window = tk.Toplevel(parent)
        self._window.title("{0} — Logs".format(PLUGIN_TITLE))
        self._window.geometry("760x520")
        self._window.columnconfigure(0, weight=1)
        self._window.rowconfigure(0, weight=1)

        body = tk.Frame(self._window)
        body.grid(row=0, column=0, sticky=tk.NSEW, padx=10, pady=(10, 0))
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)

        # Courier so the aligned configuration block stays aligned, and
        # wrap=NONE with a horizontal scrollbar so a long line is scrolled to
        # rather than reflowed — a wrapped traceback is much harder to read.
        self._text = tk.Text(body, wrap=tk.NONE, font=("Courier New", 9))
        self._text.grid(row=0, column=0, sticky=tk.NSEW)

        vertical = ttk.Scrollbar(body, orient=tk.VERTICAL, command=self._text.yview)
        vertical.grid(row=0, column=1, sticky=tk.NS)
        horizontal = ttk.Scrollbar(body, orient=tk.HORIZONTAL, command=self._text.xview)
        horizontal.grid(row=1, column=0, sticky=tk.EW)
        self._text.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)

        controls = tk.Frame(self._window)
        controls.grid(row=1, column=0, sticky=tk.EW, padx=10, pady=10)
        controls.columnconfigure(1, weight=1)

        ttk.Button(controls, text="Copy", command=self._copy).grid(row=0, column=0)
        self._note = tk.Label(controls, text="", anchor=tk.W)
        self._note.grid(row=0, column=1, sticky=tk.W, padx=(10, 0))
        ttk.Button(controls, text="Refresh", command=self._load).grid(row=0, column=2)
        ttk.Button(controls, text="Close", command=self._window.destroy).grid(
            row=0, column=3, padx=(6, 0)
        )

        self._load()

    def _load(self) -> None:
        self._text.configure(state=tk.NORMAL)
        self._text.delete("1.0", tk.END)
        self._text.insert("1.0", report(self._controller))
        # Read-only, but still selectable and still copyable by keyboard.
        self._text.configure(state=tk.DISABLED)
        self._text.see(tk.END)
        self._note.configure(text="")

    def _copy(self) -> None:
        try:
            self._window.clipboard_clear()
            self._window.clipboard_append(report(self._controller))
            # Tk's clipboard is owned by the process, so a window destroyed
            # immediately after copying can take the contents with it on some
            # window managers. update() hands it over before that can happen.
            self._window.update()
            self._note.configure(text="Copied. Paste it to an officer.")
        except tk.TclError as err:
            logger.warning("Could not copy diagnostics: %s", err)
            self._note.configure(text="Could not reach the clipboard — select and copy.")


def open_window(parent, controller) -> None:
    """Opens the log window, logging a failure rather than raising into Tk."""
    try:
        LogWindow(parent, controller)
    except Exception:
        logger.exception("Could not open the log window")
