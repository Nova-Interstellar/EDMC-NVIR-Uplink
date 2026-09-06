"""
Debug tooling, gated by DEBUG in config.py.

The main window gets a status row; the Debug button opens a window where you
pick a registered event, edit its journal fields as JSON, and send it through
the real delivery path - same extraction, same payload, same transport as a
live event.

Promotion is listed once per career, so testing a rank-up in any channel is one
pick. Preview shows the payload and where it would go, without sending.

Send posts for real, always flagged as a test so the site routes it to the
debug channel. There is no way to aim a hand-made event at a live channel: a
build with DEBUG on already sends to whichever endpoint is configured rather
than production, and the one thing left that could still reach the squadron was
this checkbox.
"""

import json
import tkinter as tk
from tkinter import ttk

from . import events, payload
from .config import DEBUG, PLUGIN_TITLE_SHORT, PLUGIN_VERSION
from .log import logger


ERROR_COLOR = "#d9534f"

# The site's own wording is written for someone reading a web page and is far
# too long for a row in EDMC's main window — it stretched the whole application
# wide. These say the same thing in a width that fits, and the settings page
# still carries the full sentence next to the field that fixes it.
SHORT_ERRORS = {
    "no_token": "No token. Check settings.",
    "unknown_token": "Token not recognised. Check settings.",
    "revoked": "Token revoked. Check settings.",
    "suspended": "Uplink paused by NVIR.",
    "unavailable": "NVIR site unreachable.",
    "no_endpoint": "Dev mode: no endpoint set.",
    # Identity. Neither stops the feed; both need something done.
    "fid_taken": "Commander linked elsewhere. Ask an officer.",
    "bad_payload": "Handshake refused. Update the plugin.",
}

FALLBACK_ERROR = "Uplink failed. Check settings."


class AppPanel:
    """
    The plugin's row in EDMC's main window.

    Its real job is failures. A send that goes wrong has nowhere else to
    surface — EDMC has no notification area, and nobody reads a plugin log —
    so a revoked token used to look exactly like a quiet evening.

    An error stays on the row until a later send succeeds. It is not a
    transient flash: the member is being asked to go and fix something, and a
    message that clears itself before they look at it may as well not exist.
    """

    def __init__(self, controller):
        self._controller = controller
        self._status = None
        self._button = None
        self._window = None
        self._error = None
        self._error_label = None

    def build(self, parent):
        # Returning one widget rather than a (label, value) pair makes EDMC
        # grid it columnspan=2 across the full width, so the title can flex and
        # push the status to the right edge — and "NVIR Uplink" does not widen
        # the narrow column shared with Cmdr, Ship and System.
        frame = tk.Frame(parent)
        frame.columnconfigure(0, weight=1)

        tk.Label(frame, text=PLUGIN_TITLE_SHORT, anchor=tk.W).grid(
            row=0, column=0, sticky=tk.EW
        )

        self._status = tk.Label(frame, text=self._idle_text(), anchor=tk.E)
        self._status.grid(row=0, column=1, sticky=tk.E)

        # Its own row underneath, so a failure never widens the window by
        # competing with the status text for the same line. Removed from the
        # grid entirely while healthy rather than left blank, which would keep
        # reserving vertical space for nothing.
        self._error_label = tk.Label(
            frame, anchor=tk.W, justify=tk.LEFT, foreground=ERROR_COLOR
        )

        # Built once and shown or hidden as the preference changes, since
        # plugin_app only runs at startup.
        if DEBUG:
            self._button = ttk.Button(
                frame, text="Debug", width=7, command=self.open_debug
            )

        self.sync()
        return frame

    def report(self, result) -> None:
        """
        Records the outcome of a send.

        Called from the delivery thread, so the widget write is marshalled back
        to the main loop — Tk is not thread-safe, and touching a label from the
        sender is the kind of bug that shows up as a frozen window weeks later.
        """
        if result.ok:
            self._error = None
        else:
            self._error = SHORT_ERRORS.get(result.code) or FALLBACK_ERROR

        if self._status is None:
            return
        try:
            self._status.after(0, self._render)
        except tk.TclError:
            pass

    def clear_error(self) -> None:
        """Called from the main loop when the member replaces their token."""
        self._error = None
        self._render()

    def _render(self) -> None:
        if self._status is None:
            return
        try:
            self._status.configure(text=self._idle_text())

            if self._error_label is None:
                return
            if self._error:
                self._error_label.configure(text=self._error)
                self._error_label.grid(row=1, column=0, columnspan=3, sticky=tk.W)
            else:
                self._error_label.grid_remove()
        except tk.TclError:
            pass

    def sync(self) -> None:
        """Match the row to the current settings."""
        self._render()

        if self._button is None:
            return
        try:
            if self._controller.settings.is_debug():
                self._button.grid(row=0, column=2, padx=(6, 0))
            else:
                self._button.grid_remove()
        except tk.TclError:
            pass

    def _idle_text(self) -> str:
        settings = self._controller.settings
        if settings.is_stealthed():
            return "Stealth"
        if settings.is_dev_endpoint():
            return "Online (Dev)"
        return "Online"

    def set_status(self, text: str) -> None:
        """Transient text from the debug window; errors have their own row."""
        if self._status is None:
            return
        try:
            self._status.configure(text=text)
        except tk.TclError:
            pass

    def open_debug(self) -> None:
        if self._window is not None and self._window.winfo_exists():
            self._window.lift()
            return
        self._window = DebugWindow(self._controller)


class DebugWindow(tk.Toplevel):
    """Compose a journal entry by hand and push it through the real path."""

    def __init__(self, controller):
        super().__init__()
        self._controller = controller

        self.title(
            "{0} debug \N{EM DASH} v{1}".format(PLUGIN_TITLE_SHORT, PLUGIN_VERSION)
        )
        self.geometry("620x620")
        self.columnconfigure(1, weight=1)
        self.rowconfigure(5, weight=1)
        self.rowconfigure(7, weight=1)

        # Promotion is listed once per career, so a rank-up in any channel is
        # one pick rather than hand-editing the career into the JSON.
        self._choices = {}
        for name in events.event_names():
            if name == "Promotion":
                for career in events.PROMOTION_CATEGORIES:
                    self._choices["Promotion / {0}".format(career)] = (name, career)
            else:
                self._choices[name] = (name, None)

        labels = list(self._choices)
        self._event = tk.StringVar(value=labels[0])
        self._cmdr = tk.StringVar(value=controller.cmdr or "Test Commander")
        self._system = tk.StringVar(value="Shinrarta Dezhra")
        self._station = tk.StringVar(value="Jameson Memorial")
        # Off by default: a debug send goes to the debug channel unless asked.

        row = 0
        ttk.Label(self, text="Event").grid(row=row, column=0, sticky=tk.W, padx=8, pady=4)
        picker = ttk.OptionMenu(
            self, self._event, labels[0], *labels, command=self._on_event_change
        )
        picker.grid(row=row, column=1, sticky=tk.EW, padx=8, pady=4)
        row += 1

        for label, var in (
            ("Commander", self._cmdr),
            ("System", self._system),
            ("Station", self._station),
        ):
            ttk.Label(self, text=label).grid(
                row=row, column=0, sticky=tk.W, padx=8, pady=2
            )
            ttk.Entry(self, textvariable=var).grid(
                row=row, column=1, sticky=tk.EW, padx=8, pady=2
            )
            row += 1

        ttk.Label(self, text="Journal fields").grid(
            row=row, column=0, columnspan=2, sticky=tk.W, padx=8, pady=(8, 2)
        )
        row += 1

        self._entry_text = tk.Text(self, height=14, wrap=tk.NONE, undo=True)
        self._entry_text.grid(
            row=row, column=0, columnspan=2, sticky=tk.NSEW, padx=8, pady=2
        )
        row += 1

        buttons = ttk.Frame(self)
        buttons.grid(row=row, column=0, columnspan=2, sticky=tk.EW, padx=8, pady=6)
        ttk.Button(buttons, text="Reset", command=self._load_sample).pack(side=tk.LEFT)
        ttk.Button(buttons, text="Preview", command=self._preview).pack(
            side=tk.LEFT, padx=(6, 0)
        )
        ttk.Button(buttons, text="Send", command=self._send).pack(
            side=tk.LEFT, padx=(6, 0)
        )
        self._target = ttk.Label(buttons, text="")
        self._target.pack(side=tk.RIGHT)
        row += 1

        self._output = tk.Text(self, height=10, wrap=tk.WORD)
        self._output.grid(
            row=row, column=0, columnspan=2, sticky=tk.NSEW, padx=8, pady=(2, 8)
        )

        self._load_sample()
        self._refresh_target()

    # --- actions ------------------------------------------------------------

    def _on_event_change(self, *_args) -> None:
        self._load_sample()
        self._refresh_target()

    def _selection(self):
        """(event name, career or None) for the current pick."""
        return self._choices.get(self._event.get(), (self._event.get(), None))

    def _load_sample(self) -> None:
        event_name, career = self._selection()
        spec = events.spec_for(event_name)
        sample = dict(spec.sample) if spec else {}

        if career:
            # Top of that career's ladder, so the sample reads as a milestone.
            table = events.RANK_TABLES.get(career, [])
            sample = {career: max(len(table) - 1, 0)}

        sample = {"event": event_name, "timestamp": payload.utc_now(), **sample}
        self._entry_text.delete("1.0", tk.END)
        self._entry_text.insert("1.0", json.dumps(sample, indent=2))

    def _destination(self) -> str:
        url = self._controller.sender.transport.url() or "no API URL set"
        return "{0}  [debug]".format(url)

    def _refresh_target(self) -> None:
        self._target.configure(text=self._destination())

    def _build_payloads(self, quiet: bool = False):
        """Zero or more payloads, exactly as a live journal entry would make."""
        raw = self._entry_text.get("1.0", tk.END).strip()
        try:
            entry = json.loads(raw)
        except json.JSONDecodeError as err:
            if not quiet:
                self._write("Journal fields are not valid JSON:\n{0}".format(err))
            return []

        event_name, _career = self._selection()
        entry.setdefault("event", event_name)
        entry.setdefault("timestamp", payload.utc_now())

        built = payload.build(
            self._cmdr.get().strip() or "Test Commander",
            entry.get("event"),
            entry,
            self._system.get().strip(),
            self._station.get().strip(),
            # Always flagged as a test, so the site routes it to the debug
            # the site routes it to the debug channel instead of the real one.
            test=True,
        )

        if not built and not quiet:
            self._write(
                "Nothing to send: {0} is not registered, its extractor "
                "rejected these fields, or nothing here maps to a "
                "channel.".format(entry.get("event"))
            )
        return built

    def _preview(self) -> None:
        built = self._build_payloads()
        if not built:
            return

        blocks = []
        for item in built:
            blocks.append(
                "POST {0}\n[{1}]\n{2}".format(
                    self._destination(),
                    item["category"],
                    json.dumps(item, indent=2),
                )
            )
        header = "" if len(built) == 1 else "{0} payloads\n\n".format(len(built))
        self._write(header + "\n\n".join(blocks))

    def _send(self) -> None:
        built = self._build_payloads()
        if not built:
            return

        self._refresh_target()
        self._write("Sending {0} payload(s)…".format(len(built)))
        for item in built:
            logger.info("Debug send: %s (%s)", item["event"], item["category"])
            self._controller.sender.submit(item, on_result=self._on_result)

    def _on_result(self, result) -> None:
        # A debug send is still a send: a token the site refuses fails here for
        # exactly the reason it will fail on a real event, so the main window
        # and the settings page hear about it too rather than the news staying
        # inside a window that gets closed.
        self._controller.note_delivery(result)

        # Runs on the delivery thread; hop back before touching any widget.
        def apply():
            lines = [
                "{0}  status={1}".format(
                    "OK" if result.ok else "FAILED", result.status
                ),
                result.detail,
            ]
            # The API echoes the embed it rendered for a debug send, so the
            # panel can show what the channel would actually see.
            embed = (result.body or {}).get("embed")
            if embed:
                lines += ["", "EMBED", json.dumps(embed, indent=2)]
            self._write("\n".join(lines))

        try:
            self.after(0, apply)
        except tk.TclError:  # window closed while the send was in flight
            pass

    def _write(self, text: str) -> None:
        self._output.delete("1.0", tk.END)
        self._output.insert("1.0", text)
