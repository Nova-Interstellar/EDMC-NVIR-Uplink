# EDMC-NVIR-Uplink internals

Developer notes for the plugin package. End-user install and settings are in
the [root README](../README.md).

## Shape

The plugin is a filter and a transport, nothing more. It decides *whether* an
event may leave the machine and *what* of it goes; nova-web decides whether the
event is worth posting and what it reads like.

```
journal_entry (EDMC main thread)
  ├─ identity.py   who this commander is — before the replay guard
  └─ journal.py    replay guard, category gate, carrier ownership
      └─ payload.py    normalise to the wire shape
          └─ sender.py     queue, hand to the delivery thread
                            (refuses outright while standing.py is latched)
              └─ transport.py  POST to nova-web
                                  └─ roster, routing, embed, Discord
```

Nothing blocks EDMC's main thread: `journal_entry` only enqueues.

| File | Holds |
| --- | --- |
| `config.py` | Build-time switches: `DEBUG`, endpoints, repo, preference keys |
| `version.py` | Update check against the published `PLUGIN_VERSION` |
| `events.py` | The registry — the one table deciding what may be sent |
| `payload.py` | The normalised wire shape |
| `transport.py` | HTTP to nova-web, retries classified |
| `sender.py` | Queue and delivery thread, rate-limit back-off |
| `standing.py` | Whether the credential is still worth using |
| `identity.py` | The handshake — FID, commander name, squadron standing |
| `journal.py` | Replay guard, category gate, carrier ownership |
| `settings.py` | Token and category choices |
| `prefs.py` | Settings tab |
| `debug_panel.py` | Main-window row and the debug window |
| `log.py` | Logger wired into EDMC's tree |
| `link-to-edmc.bat` | Links this checkout into EDMC's plugin folder |

## Working on a checkout

Double-click **`nvir/link-to-edmc.bat`**. It junctions the plugin root — its
own parent, not this package folder — into
`%LOCALAPPDATA%\EDMarketConnector\plugins`, so EDMC loads the code you are
editing and there is nothing to copy after a change. Restart EDMC to pick up
the link; after that a plugin reload is enough.

A junction needs no administrator rights. The script names the link after the
repository folder, so it survives a rename, and it clears an existing entry with
`rmdir` *without* `/s` — which removes a junction or an empty folder and fails
on anything holding files, so it can neither follow a link into your checkout
nor delete real work.

## Adding an event

Add one `EventSpec` to `events.py`:

```python
EventSpec(
    event="ShipyardBuy",
    category="trade",                  # must exist in events.CATEGORIES
    extract=_extract_shipyard_buy,     # returns a LIST of data dicts
    sample={"ShipType": "mandalay", "ShipPrice": 27452400},
)
```

`CATEGORIES` maps a channel to its checkbox label, so declaring the channel is
what creates the checkbox, picks the destination, and gates the send.
Extraction, the preferences grid and the debug form all read from that one
table, so there is no second list to update.

An extractor returns a **list**, so one journal entry can become several
payloads. `Promotion` uses this: each career is its own payload with its own
nonce, routed and retried alone. Its `category` is a function of the data
rather than a constant — the one event whose destination depends on its
contents.

Then do both halves on nova-web, or the event cannot work:

- add it to `FEED_EVENT_CHANNELS` in
  `src/data/internal/authored/squadron-feed.ts`;
- give it a describer in `src/services/squadron-feed.ts`.

The site re-derives an event's channel from its name rather than trusting the
payload's, so one it does not know is refused with **422 Not a recognised feed
event** — and one that routes but has no describer posts an embed with an empty
description. Both halves ship together, and both have to be deployed before the
plugin can send the event at all.

An extractor returns `None` to decline an occurrence: `RedeemVoucher` uses this
to drop trade dividends and scan vouchers, which share the event with bounties
but are a different activity.

## Why the wording lives on the server

`events.py` carries no copy or colours. nova-web renders the embed,
so changing what the feed says is a deploy rather than every member updating
their plugin — and there is only one implementation of each sentence.

## Things that will bite you

**EDMC 6.x widgets.** `nb.Entry` no longer exists; it is `nb.EntryMenu`. And
`plugin_prefs` is isinstance-checked against `nb.Frame`, so an error path that
returns a plain `tk.Frame` makes the whole settings tab vanish rather than show
an error. `prefs.error_frame` exists for exactly this.

**`nb.Frame` grids a spacer into row 0.** Plugin content starts at row 1.

**Tk variables are main-thread only.** The delivery thread must never touch a
`StringVar`. `Settings` keeps plain-string snapshots refreshed in `load()` and
`save()`; `transport.py` reads those. Reading a Tk variable off-thread appears
to work and then fails intermittently.

**Journal replay.** EDMC replays the current journal file on load. `journal.py`
drops anything stamped before startup. `REPLAY_GRACE_SECONDS` is not zero on
purpose: journal timestamps have whole-second precision, so an event in the same
second as startup parses as *earlier* than startup and would be dropped.

**`CarrierJump` fires for passengers.** It also carries no `CarrierID` — the
carrier is identified by `MarketID`, and `StationName` is the callsign.
`journal.py` only forwards a jump for a carrier it has seen this commander own
via `CarrierStats`, `CarrierBuy` or `CarrierJumpRequest`. The site re-checks
against the roster's carrier callsigns, since the plugin cannot be trusted.

## Endpoints

`config.py` holds them. Members never type a URL — an endpoint is squadron
infrastructure, not a preference.

- `API_BASE_URL` — the site (`https://nvir.vercel.app`).
- `API_EVENTS_PATH` — `/api/squadron/events`, the feed.
- `API_IDENTITY_PATH` — `/api/uplink/identity`, the handshake.
- Channel routing is decided on the site, not here, and officers change it on
  `/admin/config` without a deploy. The plugin never holds a Discord webhook
  URL, so a leaked EDMC config cannot post to a channel.
`Settings.base_url()` resolves it:

1. **The Dev Mode endpoint**, if both debug gates are on. It wins outright, so a
   development build cannot post into the live feed.
2. `API_BASE_URL`.

Dev Mode with an empty endpoint returns **nothing**, and the transport refuses
with `no_endpoint`. Falling back to production there would be the exact accident
Dev Mode exists to prevent: ticking the box says "not production", and a blank
field is a setting half-finished rather than permission to post to the squadron.

There is no default endpoint. A shipped one would put a single deployment's
hostname in the source of a repository that may go public, and it would be wrong
for everyone who is not the person who chose it.

A build shipped with `DEBUG = False` ignores a stored endpoint entirely, so a
developer's setting cannot follow the plugin to a member. See
[The two debug gates](#the-two-debug-gates).

Note that `test` on the payload does **not** change where the plugin posts — it
tells the site to use its debug Discord channel. Redirecting the plugin itself
is what the Dev Mode endpoint does.

## The two debug gates

Debug tooling is behind two switches, and both must be on:

1. **`DEBUG` in `config.py`** — whether the build carries the tooling at all.
   A release build ships `DEBUG = False`, and then no Development section is
   drawn and any stored debug preference is ignored outright.
2. **The Debug mode checkbox** — whether this commander has switched it on.

`Settings.is_debug()` is that `and`. It gates the Development row, the main
window's Debug button, and where events go —
`is_dev_endpoint()` is `is_debug() and dev_api_url_value`.

There used to be a third switch, a separate "use localhost" tick. It is gone,
and so is the state it made possible: development tooling running while events
still posted into the live feed, one unticked box away at all times.

The Debug button is built once at startup and shown or hidden on preference
save, because `plugin_app` only runs once — toggling it does not need a restart.

## Developing against another site

Tick **Enable Dev Mode** and type an endpoint — a local dev server, or staging.
The field appears only once the box is ticked, and the debug window's
destination line shows where a send would actually go.

Beats editing `config.py` and remembering to put it back.

A token belongs to one deployment's database, so a token from production will
not work against staging and the other way round. The settings page's profile
link points at whichever endpoint is configured, which is the point of it.

## The identity handshake

`identity.py`. Separate from the feed and sent to `/api/uplink/identity` on the
same token.

It is the only way the site can say a member is *verified*. Discord has never
heard of a Frontier id, Inara reports a name somebody typed into a form, and
neither can show the two belong together. A journal can, so what the plugin
sends is the FID, the commander name, and the squadron the game reports.

**It is state, not a stream.** The name and FID arrive once at login and do not
change again that session; squadron standing changes a few times a year. So
`Identity` folds in only the events that carry those facts and offers a payload
only when what it knows has actually moved — one request in a normal session.
Every other journal line costs a dictionary lookup.

| Journal event | Gives |
| --- | --- |
| `Commander`, `LoadGame` | `FID`, and the name (`Name` / `Commander`) |
| `SquadronStartup`, `JoinedSquadron`, `SquadronCreated` | `SquadronName`, `CurrentRank` |
| `SquadronPromotion`, `SquadronDemotion` | `SquadronName`, `NewRank` |
| `LeftSquadron`, `KickedFromSquadron`, `DisbandedSquadron` | that there is no squadron |

```json
{ "v": 1, "fid": "F366647", "commanderName": "Peanut",
  "squadron": { "name": "Nova Interstellar", "rank": 3 } }
```

Three things worth knowing about that shape:

- **The squadron is named, not numbered.** No journal event carries a squadron
  id — they all report `SquadronName` and nothing else — so the site matches the
  name against its own, case-insensitively. The contract used to ask for an id
  the plugin could never supply, which is why this half never worked; it was
  corrected in place rather than versioned, since nothing had ever sent one.
- **`squadron` absent, `null`, and present are three different things.** Absent
  means "not observed" and the site leaves stored standing alone; `null` means
  the commander left one. `SquadronStartup` only fires for a commander who is in
  a squadron, so a plugin that has not seen it cannot tell "no squadron" from
  "not looked yet", and guessing would empty the roster every time somebody
  started EDMC before the game.
- **No rank name.** The journal carries the rank number alone, so the site keeps
  whatever name the Inara scrape found rather than blanking it.

`Journal` runs this **before the replay guard**, like carrier ownership and for
the same reason: `Commander` and `LoadGame` arrive in EDMC's login replay, and
dropping them as history would leave every member unverified whenever EDMC
started after the game.

The FID is the key and the name is an attribute of it, so a commander who
renames in-game keeps their profile. The site notices the change and renames
their Discord nick to match — except for the guild owner and anyone whose
highest role sits at or above the bot's, which Discord refuses outright. Those
show as a mismatch on `/admin/members` instead.

Two refusals are terminal but say nothing about the credential: `bad_payload`
(a plugin the site no longer understands) and `fid_taken` (another profile has
claimed this commander). `standing.py` deliberately does **not** latch on
either — the token is fine and the feed has no problem — but they still surface
on the panel, because nobody would find them in a log.

## Failure handling

A refusal carries three things: `error` for the member to read, and `code` plus
`terminal` for the plugin to act on. Never match on the wording — it will change,
and it is written for a web page.

| Status | `code` | `terminal` |
| --- | --- | --- |
| 401 | `no_token`, `unknown_token`, `revoked` | yes |
| 403 | `suspended` | yes |
| 409 | `fid_taken` — identity only, does not latch | yes |
| 422 | `bad_payload` — identity only, does not latch | yes |
| 503 | `unavailable` | no |
| 429, 5xx, timeout | *(none)* | no |

`standing.py` latches on `terminal` and on nothing else — not on a status code,
and never on a response it does not understand. A proxy or a platform error page
can answer 4xx with HTML, and discarding a token over that would be worse than
retrying forever.

`unavailable` is the case the whole contract exists for. Until the site
distinguished it, a missing environment variable and a failed query were
reported as rejected credentials, and any plugin that acted on 401 would have
emptied every member's settings during one database outage.

While latched, `Sender` refuses before the wire and drops what is queued.
Holding the backlog would flush a burst of stale events the moment a new token
is pasted — and after a revoke, deliver data the squadron had decided to stop
receiving. It clears on a different token being saved, on a later success, or on
a restart, since the latch lives in memory: a suspension lifted while EDMC was
closed simply works again, at the cost of one wasted request.

Failures surface in three places, all from the same state on `Plugin`:

- the main window row, in red, shortened from `code` because the site's own
  sentences stretch EDMC's window across the screen;
- the settings page, in full, next to the field that fixes it;
- a link to the profile that issues a token.

## Update check

`version.py` reads `PLUGIN_VERSION` out of `nvir/config.py` on the repository's
default branch, so a check works without cutting a release. The fetch runs on a
background thread at plugin start and the answer is cached for the session; the
settings page renders whatever is known and updates in place when it lands.

Versions compare numerically, so `0.10.0` is correctly newer than `0.9.0`, and a
suffix like `0.4.0-rc1` degrades to `(0, 4, 0)` rather than breaking the check.

`GITHUB_REPO` is a single constant. Renaming the repository is one edit — and
GitHub redirects the old path, so an already-shipped build keeps checking
successfully in the meantime.

Bumping `PLUGIN_VERSION` and pushing is what tells every member an update
exists, so bump it in the same commit as the change you want them to take.

## Debug window

With both debug gates on, a **Debug** button appears in EDMC's main window.
Pick an event, edit its journal fields as JSON, and:

- **Preview** shows the payload and the URL it would go to. Sends nothing.
- **Send** posts it for real, always with `test` set, so the site routes it to
  the debug channel, and echoes back the embed it rendered.

There is no way to aim a hand-made event at a live channel. A "Live channel"
tick used to clear the flag; it was the last thing that could reach the squadron
from here, and removing it costs nothing a real journal entry cannot do.

Because it goes through `payload.build` and the real sender queue, it exercises
the same code a live journal entry does.

Ship a release build with `DEBUG = False`.

## Payload

```json
{
  "v": 1, "plugin": "0.5.0",
  "cmdr": "Elias Korben",
  "event": "Promotion",
  "category": "exploration",
  "at": "2026-08-30T18:04:11Z",
  "nonce": "3f2a…",
  "system": "Shinrarta Dezhra", "station": "Jameson Memorial",
  "data": { "career": "Explore", "careerLabel": "Exploration", "rank": "Elite" },
  "test": false
}
```

`at` is the journal's event time, not send time. `nonce` is per send, so a retry
that lands twice posts once — the site remembers a nonce only after it has
actually posted, so a retry after a rate-limit still gets through.
