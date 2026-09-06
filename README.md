# EDMC-NVIR-Uplink

Squadron feed for **Nova Interstellar**. Posts your rank-ups and fleet carrier
jumps to the squadron Discord, automatically, while you fly.

Only the events listed below are ever read, and only the details each one needs
are ever sent, plus one line about who you are — see
[Verifying your commander](#verifying-your-commander). Nothing else leaves your
machine.

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
| **Squadron member token** | Identifies you to the squadron site. Without it nothing is sent. Generate it on your NVIR profile — the link is on this page. |
| **Stealth mode** | Broadcasts nothing at all. Your category choices are remembered, just switched off. |
| **Broadcast** | Pick which kinds of moment you are happy to share. |

Stealth mode is there so you can go quiet for an evening without losing your
settings — tick it, and nothing you do reaches the channel until you untick it.

The top of the page shows the version you are running, and whether a newer one
has been published. Either way it links to the repository, where you can
download the latest.

## What gets posted

| Channel | You get a post when you… |
| --- | --- |
| **Trade** | Gain a Trade rank |
| **Combat** | Gain a Combat or CQC rank |
| **Exploration** | Gain an Explorer rank |
| **Exobiology** | Gain an Exobiologist rank |
| **Mercenary** | Gain a Mercenary rank |
| **Fleet Carrier** | Schedule, cancel, or complete a carrier jump |

One checkbox per channel. CQC rank-ups go out with your Combat rank, since
both are fighting. Federal and Imperial navy ranks are not carried at all, and
nothing about trading, bounties or selling data is sent.

Two details worth knowing:

- **Carrier jumps only post for your own carrier.** The game tells the plugin
  about a jump even when you are just a passenger aboard someone else's; those
  are ignored.
- **Restarting EDMC will not re-post your day.** Only things that happen while
  the plugin is running are sent.

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

The row in EDMC's main window is where failures show up. It reads **Online**
while everything is fine, and turns red with the reason when a send is refused:

| It says | What happened |
| --- | --- |
| **Token not recognised** | The token was deleted or never existed. Generate a new one. |
| **Token revoked** | An officer revoked it. Generate a new one. |
| **Uplink paused by NVIR** | Your token is real but suspended. An officer can lift it. |
| **NVIR site unreachable** | Our problem, not yours. It keeps trying. |

The first three **stop the uplink** until you paste a new token — there is no
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
— it hands events to the squadron site, which checks them and posts them. Your
token identifies you and nothing more.

Your name is checked against the Inara squadron roster. If it does not match,
nothing you send is posted; tell an officer and they can add a mapping.

## Troubleshooting

**Nothing is posting.** Look at the plugin's row in the main window first — if
something was refused, it says so there. Otherwise check that Stealth mode is
off and the box for that channel is ticked.

**It posted, then stopped.** Almost always a revoked or replaced token; the row
will say. Pasting a new one starts it again immediately, without restarting
EDMC.

**Something looks wrong.** EDMC's log has the detail —
**File → Settings → Plugins → Open Log Folder**, and search for `NVIR`.

**The settings page says "Version check unavailable".** It could not reach
GitHub. Harmless — it has no effect on whether your events are sent.

---

Developing on the plugin? See [`nvir/README.md`](nvir/README.md).
