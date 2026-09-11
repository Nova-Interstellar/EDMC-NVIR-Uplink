# EDMC-NVIR-Uplink internals

Developer notes for the plugin package. End-user install and settings are in
the [root README](../README.md).

## Shape

The plugin is a filter and a transport, nothing more. It decides *whether* an
event may leave the machine and *what* of it goes; nova-web decides whether the
event is worth posting and what it reads like.

```
journal_entry (EDMC main thread)
  ├─ identity.py   who this commander is    ─┐ both before the replay guard:
  ├─ statistics.py what they have done      ─┘ these arrive in EDMC's replay
  └─ journal.py    replay guard, Stealth gate, carrier ownership
      └─ payload.py    normalise to the wire shape
          └─ sender.py     queue, hand to the delivery thread
                            (refuses outright while standing.py is latched)
              └─ transport.py  POST to nova-web, endpoint picked by `kind`
                                  └─ roster, mutes, routing, embed, Discord
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
| `statistics.py` | Lifetime totals for the Hall of Fame, deduped by fingerprint |
| `journal.py` | Replay guard, Stealth gate, carrier ownership |
| `settings.py` | Token, Stealth, and the debug preferences |
| `prefs.py` | Settings tab |
| `debug_panel.py` | Main-window row and the debug window |
| `diagnostics.py` | The Show Logs report, masked and copyable |
| `log.py` | Logger wired into EDMC's tree, plus the ring buffer |
| `link-to-edmc.bat` | Links this checkout into EDMC's plugin folder |

## What the plugin does not decide

Which categories a member wants announced, and whether their totals feed the
Hall of Fame, both live on their NVIR profile. The site applies the choice when
a payload arrives; the plugin is never told and never asks.

That is not a division of labour, it is the only version that works. A choice
the plugin enforced would take effect at the member's next game session rather
than when they unticked the box, and a plugin on somebody else's machine can
only ever be advised. So `Settings.is_category_enabled()` and
`Settings.contributes_to_hall_of_fame()` are both `not is_stealthed()` today —
the names describe the question, not a stored answer.

Stealth Mode is the exception, and stays local for two reasons: it has to work
with the site unreachable, and it must not be something a server can switch back
on.

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

`category` must name a key in `events.CATEGORIES`, the plugin's whole idea of a
channel. It rides along on the payload, but the site re-derives the channel from
the event name rather than trusting it — see below — so the table's real job is
keeping the two codebases naming the same six things.

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

**Nothing arrives while the game is closed.** EDMC dispatches no `journal_entry`
at all with Elite not running — not a replay, not a single line. Measured, after
we told a member that restarting EDMC would push his handshake through: four log
lines, all from startup, and `Journal: NOTHING RECEIVED` in the report.

The plugin is therefore only ever fed while the game runs, and everything below
about replay means *EDMC starting while the game is already running*, in which
case it reads the in-progress journal from the top.

**Journal replay.** Starting EDMC mid-session replays the current journal file.
`journal.py` drops anything stamped before startup. `REPLAY_GRACE_SECONDS` is not
zero on purpose: journal timestamps have whole-second precision, so an event in
the same second as startup parses as *earlier* than startup and would be dropped.

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
- `API_STATS_PATH` — `/api/uplink/stats`, the Hall of Fame.
- `PROFILE_PATH` / `PROFILE_SHARING_PATH` — where the settings page's two links
  go, resolved against the endpoint in use rather than hardcoded to production.
- Channel routing is decided on the site, not here, and officers change it on
  `/admin/config` without a deploy. The plugin never holds a Discord webhook
  URL, so a leaked EDMC config cannot post to a channel.

`sender.submit(..., kind=...)` picks which of the three a payload goes to;
`transport.py` holds one method per endpoint and they share the token.

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
   A release build ships `DEBUG = False`, and then the Dev Mode section is never
   drawn and any stored debug preference is ignored outright.
2. **Enable Dev Mode** — the checkbox at the bottom of the settings page,
   whether this commander has switched it on.

`Settings.is_debug()` is that `and`. It gates the two dev fields, the main
window's Debug button, and where events go —
`is_dev_endpoint()` is `is_debug() and dev_api_url_value`.

There used to be a third switch, a separate "use localhost" tick. It is gone,
and so is the state it made possible: development tooling running while events
still posted into the live feed, one unticked box away at all times.

The Debug button is built once at startup and shown or hidden on preference
save, because `plugin_app` only runs once — toggling it does not need a restart.

## Developing against another site

Tick **Enable Dev Mode**, then fill in the two fields that appear: **Dev
endpoint** (a local dev server, or staging) and **Dev token**. Both are hidden
until the box is ticked rather than greyed out, and the debug window's
destination line shows where a send would actually go.

Beats editing `config.py` and remembering to put it back.

The dev token is stored separately from the squadron one, and
`Settings.token_value()` returns whichever matches the endpoint in use. A token
belongs to one deployment's database, so pasting a staging token over your live
one is a quiet way to break your own uplink and not notice until a rank-up goes
missing. The settings page's profile links point at whichever endpoint is
configured, for the same reason.

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

## Statistics and the Hall of Fame

`statistics.py`. Its own endpoint, `/api/uplink/stats`, on the same token.

Elite writes one journal event, `Statistics`, carrying every lifetime total it
tracks — sixteen sections, roughly two hundred numbers, all at once. That is the
entire dataset the Hall of Fame ranks, and it costs nothing to collect because
the game was writing it anyway.

```json
{ "v": 1, "statistics": { "Combat": { "Bounties_Claimed": 412, … }, … } }
```

Three things decide the shape:

- **Sent whole.** The site chooses which numbers become boards, so forwarding
  everything is what lets NVIR add one without shipping a plugin release. The
  plugin's only question is whether to send at all.
- **State, not a stream.** The event is already cumulative, so there is nothing
  to accumulate here — the plugin forwards the latest and the site keeps exactly
  one row per member.
- **Deduped by fingerprint.** `Statistics` fires far more often than it changes
  (measured at thirty-two times in one session), so `observe()` compares sorted
  JSON of the payload against what was last *accepted*, not against whether one
  has been seen. Two hundred fields compared by value would be a dictionary walk
  per journal entry.

Run ahead of the replay guard, like the handshake and for the same reason:
`Statistics` arrives in EDMC's login replay, so treating it as history would mean
a member only ever contributed when they alt-tabbed mid-game.

`hall_of_fame_off` is the one refusal worth knowing about. The member deleted
their record and opted out, so `Statistics.refuse()` stops offering for the rest
of the session rather than posting the same rejection at every login. It clears
on a new token, since that is a different profile as far as the site is
concerned. It does **not** latch the credential — the token is fine.

## State that arrives once

`Identity` and `Statistics` both fold journal entries into what they know and
offer a payload when it moves. The trap is that `observe` can only answer while
the entry is *in hand*, and the entries carrying this state arrive at login:
`Commander` and `LoadGame` once each, `Statistics` when the game feels like it,
the squadron events a few times a year.

So clearing what was accepted is never enough on its own. A token pasted
mid-session -- which is every first-time setup, since the token is the reason
the plugin was installed -- would wait for an entry that is not coming until the
next game start, with the panel reporting Online throughout. That is exactly how
one member spent a session unverified and off the boards.

Both therefore answer the same question without an entry, through `pending()`,
and `Journal.resend_state()` offers whatever the session already knows the
moment `Settings.on_token_changed` fires. Statistics is gated on Stealth there
exactly as `_contribute` gates it; identity is not, for the same reason
`_handshake` is not.

`resend_state` can only offer what this EDMC session has already seen, and with
the game closed that is nothing — EDMC dispatches no entries at all. So a token
pasted with Elite shut still sends nothing, and correctly so: there is nothing to
send. The report says `not observed yet` rather than implying a failure, and the
member's next login fills it in.

Anything else that becomes "state the site needs" belongs in the same shape:
fold, `pending()`, and a line in `resend_state`.

## Diagnostics

`diagnostics.py`, reached from **Show logs** on the settings page. It assembles
the configuration, what the session has learned, and every line the plugin has
logged, then masks the secrets so the whole thing can be pasted into Discord.

The log comes from a ring buffer in `log.py` -- a `logging.Handler` on our own
logger keeping the last `RECENT_LIMIT` formatted records. Our logger is set to
DEBUG so the buffer sees everything regardless of EDMC's level; EDMC's handlers
still apply their own, so a member running at INFO does not get our debug lines
in their file.

Two rules when adding to it:

- **Log the decision, not just the outcome.** "No handshake to re-send yet" is
  worth a line precisely because nothing happened -- a silent uplink is the
  failure mode, so silence in the log is the one thing that cannot be read.
- **Mask anything that authenticates.** `log.mask` gives first and last three,
  which identifies a token without being one. It is covered by a test that puts
  every secret through `report()` and asserts none survives whole.

`Journal.summary()`, `Identity.summary()` and `Statistics.summary()` exist for
this report and nothing else. They are what distinguishes "never had anything to
send" from "sent it and was refused", which is otherwise invisible from outside
the process.

## Failure handling

A refusal carries three things: `error` for the member to read, and `code` plus
`terminal` for the plugin to act on. Never match on the wording — it will change,
and it is written for a web page.

| Status | `code` | `terminal` |
| --- | --- | --- |
| 401 | `no_token`, `unknown_token`, `revoked` | yes |
| 403 | `suspended` | yes |
| 409 | `fid_taken` (identity), `hall_of_fame_off` (statistics) — neither latches | yes |
| 422 | `bad_payload` — does not latch | yes |
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

The picker holds feed events only. The handshake and statistics are not
hand-sendable — both are state folded out of journal entries rather than built
from a form, so the way to exercise them is to point Dev Mode at a local site
and start the game.

Ship a release build with `DEBUG = False`.

## Payload

```json
{
  "v": 1, "plugin": "0.8.0",
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
