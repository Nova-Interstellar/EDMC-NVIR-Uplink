# EDMC-NVIR-Uplink

Squadron uplink for **Nova Interstellar**. It announces your rank-ups and fleet
carrier jumps in the squadron Discord, marks you verified on the roster, and
feeds your in-game totals to the squadron Hall of Fame — all while you fly.

It reads your game journal, the same file EDSM and Inara already read, and
nothing else on your machine. What it is allowed to send is yours to choose, and
lives on your NVIR profile.

## Install

1. Download the plugin and unzip it into EDMC's plugin folder:

   ```
   %LOCALAPPDATA%\EDMarketConnector\plugins\EDMC-NVIR-Uplink
   ```

   In EDMC you can get there with **File → Settings → Plugins → Open**.

2. Restart EDMC.
3. Sign in at [nvir.vercel.app](https://nvir.vercel.app) with Discord, open
   your profile, and generate an uplink token.
4. Open **File → Settings → NVIR Uplink** and paste it in. The settings page
   also links straight to your profile if you need to get back there.

That is the whole setup. There is no URL to configure — the plugin already
knows where to send things.

The token is yours alone. It is shown once and stored only as a hash, so nobody
— including an officer — can read it back; if you lose it, generate another and
the old one stops working. You need to be a member of the squadron Discord to
have a profile at all.

Requires EDMC 6.x.

## Settings

**File → Settings → NVIR Uplink**

| Setting | What it does |
| --- | --- |
| **Squadron Member Token** | Identifies you to the squadron site. Without it nothing is sent. Generate it on your NVIR profile — the link is on this page. |
| **Stealth Mode** | Sends nothing at all, whatever your profile says. Your choices are remembered, just switched off. |
| **Open my profile** | Opens the part of your profile that decides what the uplink may publish. |
| **Show logs** | Everything the plugin has done since EDMC started, with your token hidden. Copy it to an officer when something is not working. |

Stealth Mode is there so you can go quiet for an evening without changing
anything: tick it, and nothing leaves your machine until you untick it. It is
the one switch that lives here rather than on the site, because "send nothing"
has to work with the site unreachable.

The top of the page shows the version you are running, and whether a newer one
has been published. Either way it links to the repository, where you can
download the latest.

## What you share

Everything the uplink publishes is decided on your
[profile](https://nvir.vercel.app/profile#uplink), each with its own switch:
which rank-ups and carrier jumps get announced, and whether your totals count
towards the Hall of Fame. Changes apply straight away — there is nothing to
restart and no plugin update to wait for.

Turning the Hall of Fame off also deletes what NVIR holds for you and refuses
any more, so your next session will not quietly put it back.

## What gets posted

| Channel | You get a post when you… |
| --- | --- |
| **Trade** | Gain a Trade rank |
| **Combat** | Gain a Combat or CQC rank |
| **Exploration** | Gain an Explorer rank |
| **Exobiology** | Gain an Exobiologist rank |
| **Mercenary** | Gain a Mercenary rank |
| **Fleet Carrier** | Schedule, cancel, or complete a carrier jump |

CQC rank-ups go out with your Combat rank, since both are fighting. Federal and
Imperial navy ranks are not carried at all, and nothing about trading, bounties
or selling data is sent.

Two details worth knowing:

- **Carrier jumps only post for your own carrier.** The game tells the plugin
  about a jump even when you are just a passenger aboard someone else's; those
  are ignored.
- **Restarting EDMC will not re-post your day.** Only things that happen while
  the plugin is running are sent.

## Hall of Fame

The game keeps a running tally of everything you have done — systems visited,
bounties claimed, organics scanned — and writes it into your journal. The
plugin forwards that tally, and the squadron
[Hall of Fame](https://nvir.vercel.app/squadron/hall-of-fame) ranks it.

Only the latest tally is kept, one per member, and names are shown masked. The
boards are decided on the site, so NVIR can add one without you updating
anything.

## Verifying your commander

Once per session the plugin tells the site your commander name, your Frontier id
(`F366647` and the like), and which squadron the game says you are flying under.
That is what makes you **verified**: Discord has never heard of your commander,
and a name typed into a form proves nothing on its own.

None of it is private. Anyone who drops into the same instance sees your
commander name, and the squadron tag is on your ship. It is also not sent per
event — once when the game loads, and again only if something changes.

Rename your commander in-game and the site follows you: your profile keeps its
history and your Discord nickname is updated to match. The bot cannot rename the
server owner, or anyone whose highest role sits at or above its own, so those are
flagged for an officer to change by hand.

## When something is wrong

The row in EDMC's main window says what the uplink is doing:

| Row | Meaning |
| --- | --- |
| **Online** | A token is set and nothing has been refused. |
| **Stealth** | Stealth Mode is ticked. Nothing is being sent, by your choice. |
| **Offline** | No token. Nothing can be sent until you paste one. |
| **Error** | A send was refused. The reason is in the box underneath. |

**Offline** and **Error** are red, and a box appears under the row with the
detail:

| It says | What happened |
| --- | --- |
| **No token** | Nothing pasted in yet. Generate one on your profile. |
| **Token not recognised** | The token was deleted or never existed. Generate a new one. |
| **Token revoked** | An officer revoked it. Generate a new one. |
| **Uplink paused by NVIR** | Your token is real but suspended. An officer can lift it. |
| **Commander linked elsewhere** | Another profile has claimed your commander. Ask an officer. |
| **Hall of Fame off** | Your totals were offered while it is switched off. Re-enable it on your profile, or ignore this. |
| **Handshake refused** | The site no longer understands this version. Update the plugin. |
| **NVIR site unreachable** | Our problem, not yours. It keeps trying. |

The first four **stop the uplink** until you paste a new token — there is no
point asking the site about a credential it has already rejected, and doing so
on every jump would bury anything else in the log. Anything still queued is
dropped rather than saved up, so replacing a token does not flush an evening of
stale events into the channel.

The last one is not treated as your problem at all. A site outage keeps
retrying and never asks you to change anything, which is the distinction the
whole thing turns on: if the squadron site is having a bad minute, your token
was never wrong.

The settings page shows the same failure in full, next to the field that fixes
it.

## Privacy

The plugin holds no Discord webhook, so it cannot post to the channel directly
— it hands what it reads to the squadron site, which checks it and decides what
to publish. Your token identifies you and nothing more.

Your name is checked against the Inara squadron roster. If it does not match,
nothing you send is posted; tell an officer and they can add a mapping.

Your profile lists everything NVIR holds for you, and switching something off
there stops it at the site, not just on your machine.

## Troubleshooting

**Nothing is posting.** Look at the plugin's row in the main window first — if
something was refused, it says so there. Otherwise check that Stealth Mode is
off, and that the category is still switched on for you on your
[profile](https://nvir.vercel.app/profile#uplink).

**It posted, then stopped.** Almost always a revoked or replaced token; the row
will say. Pasting a new one starts it again immediately, without restarting
EDMC.

**Nothing of mine is in the Hall of Fame.** The game writes your totals when you
start a session, so they arrive on your next one with the plugin running. Your
profile says what is stored.

**Something looks wrong.** **File → Settings → NVIR Uplink → Show logs**, then
**Copy**, and send it to an officer. It carries what the plugin is set to do and
everything it has done this session, with your token masked — it is safe to
paste as it stands, and it usually answers the question on its own.

**The settings page says "Version check unavailable".** It could not reach
GitHub. Harmless — it has no effect on whether your events are sent.

---

Developing on the plugin? See [`nvir/README.md`](nvir/README.md).
