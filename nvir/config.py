"""
Static configuration for the NVIR plugin.

Everything here is set in source and ships the same for everyone. Endpoints are
squadron infrastructure, not a member's choice, so they live here rather than in
preferences — a commander should never have to paste a URL to use the plugin.

The only per-commander settings are the squadron token and which categories to
broadcast; those live in `settings.py`.
"""

PLUGIN_NAME = "NVIR Uplink"
PLUGIN_TITLE = "Nova Interstellar Uplink"
# For the main EDMC window, where the row shares a narrow column with the
# commander, ship and system fields.
PLUGIN_TITLE_SHORT = "NVIR Uplink"
PLUGIN_VERSION = "0.7.0"

# --- Repository --------------------------------------------------------------
# One constant so a repo rename is a single edit. GitHub redirects the old path
# for a renamed repo, so an outdated build keeps checking successfully.

GITHUB_REPO = "Nova-Interstellar/EDMC-NVIR-Uplink"
GITHUB_URL = f"https://github.com/{GITHUB_REPO}"
GITHUB_BRANCH = "main"

# The published version is read from this file's own PLUGIN_VERSION on the
# default branch, so a check works without cutting a release.
VERSION_SOURCE_URL = (
    f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}/nvir/config.py"
)

# An update check must never hold up the settings page.
VERSION_CHECK_TIMEOUT = 6

# Shows the debug panel in the main EDMC window: pick an event, edit its
# fields, send it through the real delivery path. Turn off for a release build.
DEBUG = True

# --- Endpoints ---------------------------------------------------------------
# Events go to the nova-web API, which checks them against the squadron roster,
# applies the thresholds, renders the embed and posts it to Discord. No webhook
# URL ever reaches a member's machine: the site holds those, so a leaked EDMC
# config exposes nothing and channels can be re-routed without a plugin update.

API_BASE_URL = "https://nvir.vercel.app"

API_EVENTS_PATH = "/api/squadron/events"

# The identity handshake: FID, commander name and squadron standing, taken from
# a running game session. It is what makes a member "verified" on the site —
# Discord does not know a commander's FID, Inara reports a name somebody typed,
# and neither can prove the two belong together.
#
# Sent at most a handful of times a session, not per event: it is state, and the
# plugin skips a resend that would say exactly what the last one did.
API_IDENTITY_PATH = "/api/uplink/identity"

# Commander statistics, for the squadron Hall of Fame. One journal event holds
# every number the boards rank, so this is the whole of it, sent when it moves.
#
# The site decides what is ranked and what is shown; the plugin's only question
# is whether to send at all. That is why there is one setting here rather than a
# checkbox per section — changing the boards must never need a plugin release.
API_STATS_PATH = "/api/uplink/stats"

# Where a member generates their token. Resolved against whichever site the
# plugin is pointed at, so a development build links to that site's profile
# rather than sending someone to production for a token that will not work
# there — tokens live in a database, and each deployment has its own.
PROFILE_PATH = "/profile"

# Where a development build sends is typed in by whoever is developing, and
# defaults to nothing. A shipped default would put one deployment's hostname in
# the source of a repository that may go public, and it would be wrong for
# everyone who is not the person who chose it.

USER_AGENT = f"EDMC-NVIR/{PLUGIN_VERSION}"
HTTP_TIMEOUT = 10

# Give up on an event after this many failed attempts.
MAX_ATTEMPTS = 3

# Journal entries older than this many seconds before plugin start are treated
# as replay and dropped. EDMC replays the current journal file on load.
#
# The grace absorbs the game's whole-second timestamps: an event happening in
# the same second the plugin starts would otherwise parse as earlier than
# startup and be dropped. Replayed history is minutes to hours old, so a few
# seconds of slack costs nothing.
REPLAY_GRACE_SECONDS = 5

# --- Preference keys ---------------------------------------------------------

KEY_API_TOKEN = "nvir_api_token"
KEY_STEALTH = "nvir_stealth"
KEY_HALL_OF_FAME = "nvir_hall_of_fame"
# Retired: which channels broadcast moved to the member's NVIR profile, where
# the site applies it on arrival. Kept only so the stored values can be cleaned
# up on load; nothing reads them.
LEGACY_CATEGORY_KEY = "nvir_category_{0}"

# Debug-only, and only honoured while DEBUG is on: a build shipped with
# DEBUG = False ignores whatever these hold.
KEY_DEBUG_MODE = "nvir_debug_mode"
KEY_DEV_API_URL = "nvir_dev_api_url"

# The endpoint used to live behind a second "use localhost" checkbox. Debug mode
# now implies it, so the old value is carried across once and the key dropped.
LEGACY_DEV_URL_KEY = "nvir_localhost_url"

# Settings retired as the plugin moved to the squadron API. Any value still
# stored under these keys is deleted on load, so no webhook URL or hand-typed
# endpoint lingers in a member's EDMC config.
RETIRED_KEYS = (
    # Per-channel broadcast choices, now on the profile page.
    "nvir_category_trade",
    "nvir_category_combat",
    "nvir_category_exploration",
    "nvir_category_exobiology",
    "nvir_category_mercenary",
    "nvir_category_carrier",
    "nvir_use_localhost",
    "nvir_webhook_url",
    "nvir_option_trade.sales",
    "nvir_option_trade.ranks",
    "nvir_option_combat.vouchers",
    "nvir_option_combat.ranks",
    "nvir_option_combat.cqc",
    "nvir_option_exploration.sales",
    "nvir_option_exploration.ranks",
    "nvir_option_exobiology.sales",
    "nvir_option_exobiology.ranks",
    "nvir_option_mercenary.ranks",
    "nvir_option_carrier.jumps",
    "nvir_api_url",
    "nvir_api_url_debug",
    "nvir_api_url_trade",
    "nvir_api_url_combat",
    "nvir_api_url_exploration",
    "nvir_api_url_exobiology",
    "nvir_api_url_milestones",
    "nvir_api_url_carrier",
)


def squadron_url() -> str:
    """
    The live endpoint.

    A debug send goes here too. `test` on the payload tells the site to post it
    to the debug Discord channel; it does not change where the plugin posts.
    Redirecting the plugin itself is what Debug mode's endpoint field does.
    """
    return API_BASE_URL
