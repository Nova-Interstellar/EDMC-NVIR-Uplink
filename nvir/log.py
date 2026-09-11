"""
Logger wired into EDMC's logging tree, with a standalone fallback.

Everything the plugin logs is also kept in memory, so the settings page can show
a member their own uplink's history without sending them into EDMC's log folder
to find our lines among every other plugin's. A report that takes one button is
a report we actually get.

The buffer is capped and holds formatted strings, so a long session cannot grow
it and nothing in it can still be mutated by the code that logged it.
"""

import logging
import os
from collections import deque
from datetime import datetime

# The folder EDMC loaded the plugin from. In the report because it catches the
# commonest bad install on sight: GitHub's ZIP unpacks to
# "EDMC-NVIR-Uplink-main", and a second folder around that is why EDMC finds
# nothing at all.
PLUGIN_DIR = os.path.basename(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_plugin_dir = PLUGIN_DIR

try:
    from config import appname  # type: ignore

    logger = logging.getLogger(f"{appname}.{_plugin_dir}")

except ImportError:  # running outside EDMC, e.g. a unit test
    logger = logging.getLogger(_plugin_dir)

# Roughly a long session's worth. Old lines are the ones that stop mattering:
# what a member needs to paste is what just happened.
RECENT_LIMIT = 500
_recent = deque(maxlen=RECENT_LIMIT)


class _RingBuffer(logging.Handler):
    """Keeps the last few hundred of our own records, formatted."""

    def emit(self, record: logging.LogRecord) -> None:
        # A logging handler that raises takes the caller down with it, and the
        # callers here are journal handling and the delivery thread.
        try:
            _recent.append(
                "{0} {1:<7} {2}".format(
                    datetime.fromtimestamp(record.created).strftime("%H:%M:%S"),
                    record.levelname,
                    self.format(record),
                )
            )
        except Exception:
            pass


# DEBUG on our own logger, so the buffer sees everything the plugin says
# whatever EDMC's level is. EDMC's handlers still apply their own, so a member
# running EDMC at INFO does not get our debug lines in their file.
logger.setLevel(logging.DEBUG)

_buffer = _RingBuffer()
_buffer.setFormatter(logging.Formatter("%(message)s"))
logger.addHandler(_buffer)

if len(logger.handlers) == 1 and not logger.parent.hasHandlers():
    # Outside EDMC there is nothing else listening, so keep the console output
    # the fallback always had. The ring buffer does not count as somewhere a
    # developer can read.
    console = logging.StreamHandler()
    console.setFormatter(
        logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    )
    logger.addHandler(console)


def recent() -> list:
    """Every line the plugin has logged this session, oldest first."""
    return list(_recent)


def mask(value, keep: int = 3) -> str:
    """
    A secret, shown as much as identifies it and no more.

    `abc…xyz` is enough for a member to confirm they pasted the token they meant
    to, and enough for us to tell two tokens apart in a paste, without being
    enough to use. Anything too short to mask that way is replaced outright
    rather than half-shown.
    """
    text = str(value or "")
    if not text:
        return "(not set)"
    if len(text) <= keep * 2:
        return "*" * len(text)
    return "{0}{1}{2}".format(text[:keep], "*" * (len(text) - keep * 2), text[-keep:])
