---
name: coh3-replay-analysis
description: Analyse a Company of Heroes 3 match and write a coaching-style report. Two data sources, fused: coh3stats.com / Relic's API supplies end-game stats the replay can't (kills, losses, damage, vehicles killed/lost, captures, veterancy, authoritative win/loss), and the replay (.rec) supplies the input signatures — build orders, retreats, abilities, chat, territory and lane control — decoded from the raw binary. Preferred entry point is a coh3stats match URL or id (pulls stats and auto-downloads the replay); a loose .rec, or an OCR'd post-game screenshot, are fallbacks. Use this skill whenever someone links a coh3stats match, uploads or points at a .rec file, mentions a CoH3 replay, asks "why did we lose that game", asks for a post-game breakdown, MVP/worst-player calls, build-order review, or any analysis of a Company of Heroes 3 match — even without the words "replay" or "rec file". The format is undocumented and guessing at it produces confidently wrong player attributions, so always parse rather than guess.
---

# CoH3 replay (.rec) analysis

A `.rec` is Relic's deterministic **input log**. It records every command every
player issued, with tick timestamps and world coordinates. The game recreates
the match by replaying those inputs through the engine.

That single fact governs everything here.

## What is and is not in the file

**Present:** players, factions, teams, slot ids, map, duration, every command
with its tick and (for positional commands) x/z coordinates, unit production
with blueprint ids, ability and upgrade use, battlegroup purchases, chat
messages, surrender events.

**Absent:** kills, losses, damage, squad wipes, veterancy, victory-point
tickers, resource income, unit health, what any player could see. None of it
exists until the engine re-simulates.

So you can say *"DeathStyle retreated nine squads in twenty seconds"* — that is
a recorded input. You cannot say *"DeathStyle lost his Panzergrenadiers to a
flank"* — that is fiction. When you want to describe a fight, describe the
**input signature** of the fight (retreat bursts, ability spikes, production
responses, territory swings) and let the reader infer the rest. Users will ask
for kill counts and win/loss stats; tell them plainly the format does not carry
them rather than estimating.

## Primary workflow: start from the coh3stats match

The best report fuses two sources, and **one command pulls both**:

```bash
python3 scripts/coh3stats.py match <coh3stats-match-URL-or-id>
```

e.g. `... match https://coh3stats.com/matches/84033636` (a bare id works too).
It:

1. fetches Relic's **end-game stats** from coh3stats — per player: kills
   (`ekills`/`sqkill`/`vkill`), losses (`edeaths`/`sqlost`/`vlost`/`vabnd`),
   damage, captures, veterancy — plus the **authoritative win/loss** (Relic
   records who won; no need to infer it from a surrender);
2. downloads the **replay** and runs the full input-signature analysis under it
   (everything `analyze_rec.py` prints — build orders, retreats, territory).

**The two layers answer different questions and must stay labelled:**

- **API = what happened.** Outcomes the engine simulated: who killed and lost
  what, damage, captures, final veterancy.
- **`.rec` = how they played.** The recorded inputs: build order, production
  gaps, retreat bursts, territory and lane structure.

Never fuse them into one sentence. "OstwindRush got 101 kills for 37 losses"
(API) and "OstwindRush sat at 90% own-half" (`.rec`) are both true and together
tell the story — but an API kill count welded into a `.rec` claim is the exact
fabrication this skill exists to prevent. Read them side by side; the tension
between them is usually the insight (most-active player, lowest damage; passive
player, best trades).

**The anchor.** `python3 scripts/coh3stats.py player` (no args) prints the
anchor's long-term record across modes/factions; the match report centres on the
anchor's team and flags them with `*`. The anchor is **DeathStyle (#1101261)**.
The friend group plays as a **2–4 stack, sometimes with randoms filling the
rest**, so teammates change game to game — learn who recurs rather than assuming
a fixed roster. Override per run with `--anchor <profile_id>`, or pass any
profile id/URL to `player`.

**Constraints (verified against the live service):**

- **Automatch only.** coh3stats has ranked and unranked automatch plus vs-AI.
  Pure custom lobbies (matchtype `Custom`) are not there; if `match` errors that
  the id is unknown, the game wasn't tracked — fall back to a supplied `.rec`.
- **The replay sometimes needs one manual click.** The direct download works
  only once coh3stats has *materialised* the `.rec`; generating a missing one is
  behind a browser challenge a script can't pass. If the command says the replay
  isn't available, open the match page, click **Download Replay**, then re-run
  with `--rec <downloaded.rec>`. The end-game stats stand on their own meanwhile.
- **Site down / not on coh3stats.** Fall back to the `.rec`-only path below, and
  for the combat numbers, OCR of the in-game **post-game score screen** the user
  screenshots — fold it in labelled *screen-reported*, same footing as the API.

Useful flags: `--rec <file>` (skip the download, use a local replay),
`--no-replay` (end-game stats only), `--anchor <id>`, `--json <out>`.

## The `.rec` layer (driven by the above, or run standalone)

```bash
python3 scripts/analyze_rec.py /path/to/replay.rec
```

Use this directly when you have a loose `.rec` and no coh3stats match (custom
games, or a file a friend hands you). It prints the whole input-signature
evidence brief: match header, per-player totals, build orders, production gaps,
squad composition, vehicle timeline, retreat bursts, activity and attack
timelines, territory/lane analysis, abilities, battlegroup purchases, chat,
anomalies, and a command histogram. Read it, then write the report. Useful flags:

- `--json out.json` — structured output alongside the text
- `--no-lookup` — skip blueprint names (instant, but no unit names or vehicle
  classification). Only for a quick sanity peek.
- `--block N` — timeline granularity in minutes (default 3; use 2 for games
  under 15 minutes, 5 for games over 35)
- `--cache PATH` — where to keep the blueprint id table

The first run downloads ~110 MB of blueprint data from the `cohstats/coh3-data`
repo and caches a small lookup table (`coh3_pbgid_cache.json`). That takes a
minute or two; every run after it is instant. If the download fails, the parser
still works — you just get raw `pbgid:198340` instead of `panzergrenadier_ak`.

For anything the script doesn't cover, import the parser directly:

```python
import sys; sys.path.insert(0, 'scripts')
from coh3rec import Replay, load_lookup, team_anchors, make_projector, mmss
r = Replay('game.rec')
lookup = load_lookup()
[c for c in r.commands if c.type == 78]   # every retreat
```

`references/rec-format.md` has the byte-level `.rec` format if the parser ever
breaks on a new patch; `references/coh3stats-api.md` documents the coh3stats /
Relic API endpoints, the `counters` fields, and the replay-download mechanics if
that side ever needs fixing.

## Two checks before you write anything

**1. Verify the slot mapping.** The script prints `slot check`. Player records
in the header are **not** stored in slot order, and the slot field — not header
position — is the id used in the command stream. Get this wrong and every
per-player judgement lands on the wrong human, which is the worst possible
failure mode for this skill. The check cross-references each slot's built units
against its header faction; if it reports a mismatch, stop and investigate
rather than publishing. Two Wehrmacht players on the same team are
indistinguishable by faction alone, so this check is the only thing standing
between you and a confident misattribution.

**2. Verify the outcome.** If you came in through `coh3stats.py match`, the API
states the winner authoritatively (`result team N WON`) — use it and move on.
Working from a bare `.rec`, the only outcome the file states directly is a
concede: `PCMD_Surrender` commands from **every** member of one side. If the
script says no surrender was recorded, the match ended by annihilation, VP
depletion, or a drop, and **the file does not say who won** — say so rather than
inferring it from who looked stronger. (A partial concede — some but not all of a
side — is not a team result either; the script now labels that case explicitly.)

(A third check, once you reach the territory section: if the anchor warning
fires, resolve it before quoting depth numbers. See below.)

Also check the premise you were given. Users misremember which game they
uploaded and which side they were on. If the file contradicts them — they say
they lost and the enemy conceded — lead with that correction before anything
else. Being agreeable about it wastes their time.

## Reading the tables

**CPM (non-camera commands per minute)** is the workhorse activity metric.
Command types 157 (camera) and 158 (a ~2s per-player sync heartbeat) are engine
noise and are excluded. Real CPM is roughly a third of the in-game APM display.
Rough calibration: under 25 is a passenger, 30–50 is a competent team-game
player, 80+ is a high-tempo player. A 2× team-level gap in total commands is by
itself a sufficient explanation for a loss.

**Build orders and production gaps.** Gaps over ~2.5 minutes and a late "last
build" are the clearest macro failures in the file, and they are unambiguous —
no inference needed. Always check gaps against the battlegroup ability list
before calling someone lazy: a player running a call-in battlegroup legitimately
builds fewer squads from buildings. Low *activity* is never excused that way.

**Vehicle timeline.** Usually the single most explanatory table. Classification
comes from the blueprint category, not name matching — `panzergrenadier`
contains `panzer` but is infantry. Look at the tank/TD counts and, more
importantly, at *when* each side's armour clusters. A late flood of enemy armour
against a static defender is what most team-game losses actually look like.

**Retreat bursts** (≥3 retreats within 30s) mark the moments a player pulled a
lot of units out at once. That is where the big fights were. Note the direction
of inference: a burst means units were saved, which usually means a fight was
going badly — but a burst on the *enemy* side means your team was winning that
exchange. In the 4v4 test case the losing team's best moment was visible only as
nine enemy retreats in twenty seconds.

**Territory.** Depth runs 0 (Axis base) to 100 (Allied base). Because "forward"
is the opposite direction for each side, **the two team rows are not directly
comparable** — read the `FRONT LINE` row, their midpoint: above 50 means play is
happening in Allied territory, below 50 means the Axis is pinned back.

Base anchors are *estimated* from each player's first positional order, and that
estimate can fail. A player whose opening order is already at midfield drags his
side's anchor inward, which inflates every depth number on the board — observed
in testing producing a front line of 58-68 where the truth was 48-59. The
estimate can only ever be dragged toward the centre, never away, so the script
prints an anchor-symmetry ratio and warns below 0.85.

**When you see that warning, check it before quoting any depth figure.** The
per-player first-order positions are printed right there: if one side's players
opened at a tight cluster near a map corner and the other side's are scattered
inward, the scattered side's anchor is wrong. Re-run with the good side's corner
and a plausible mirror:

```bash
python3 scripts/analyze_rec.py game.rec --anchors '142,127:-130,-140'
```

Auto-correction was tried and deliberately rejected — reflecting the good anchor
through the map centre fixes some maps and throws others off by 100+ units,
because bases are not reliably symmetric. A human-checkable warning beats a
heuristic that is silently wrong. Either way the *trend* is robust even when the
magnitudes are off; lead with the trend.

**Lane assignment.** `lateral` is signed offset perpendicular to the base-to-base
axis. Teammates within ~40 units of each other are contesting the same corridor.
Two teammates stacked in one lane while a flank goes 1v1 is a real and common
strategic error that is invisible without this projection.

**Anomalies.** `PCMD_AIPlayer` events, long command gaps, and an outlier-low
camera count can indicate a disconnect or AI handover. Flag these as possible,
not confirmed — the meanings are reverse-engineered.

## Writing the report

Default structure, unless the user asks for something else:

```
1. Match header — map, mode, duration, roster with factions, and the outcome.
   With coh3stats the winner is authoritative; from a bare .rec it's the concede
   at MM:SS, or "file does not record a winner".
2. One short paragraph naming the two layers you're working from — Relic's
   end-game stats (what happened) and the replay inputs (how they played) — or,
   .rec-only, what a replay can and can't show.
3. Top-level findings — 4 to 7 numbered items, each anchored to a specific
   number or table. The strongest ones cross the layers: kills-vs-losses and
   damage (API) set against activity, armour timing, lane structure and
   territory trend (.rec). Macro blackouts, unused mechanics.
4. The deciding moments — timestamped, described by input signature, with the
   end-game toll where it sharpens the point (a retreat burst that shows up as
   squads lost; an armour push that shows up as vehicle kills).
5. Repeated issues — patterns that recur, especially across multiple replays
   from the same group (see the anchor's match history for who keeps repeating
   which mistake).
6. Per-player breakdown — for each player, genuine strengths first with the
   evidence, then the sharp criticism with the evidence. Both halves must cite
   numbers; unsupported praise is as useless as unsupported blame. When the two
   layers disagree — busiest player, worst trades; quiet player, best K/D — say
   so; that gap is often the most useful thing in the report.
7. MVP and a wooden-spoon pick, one line each, each justified by a stat. Prefer
   an outcome stat (kills/losses/damage) over raw activity for these calls —
   activity is effort, not impact.
```

Cover the user's own team in depth and the opposition briefly, unless asked
otherwise. If the user asks for the analysis of a side other than the one they
named, give them what the file supports.

Tone: direct and specific. These reports are for players who want to improve, so
soft-pedalling wastes the reading. But the "uninstall"/worst-player framing is
banter between teammates — deliver it as a data-backed verdict with a reason,
not as contempt, and never extend it to opponents who aren't in the room. If the
chat log contains abuse, report it factually as part of that player's read; it
is a real team-game problem, but don't sermonise.

Every claim traces to a table. If you can't point at the number, cut the line.

## Worked examples

**Describing a fight.**
- Bad: *"He lost his squads in a bad engagement at the north VP and never
  recovered."* — kills, positions and causation the file doesn't contain.
- Good: *"15:41–16:01 — poker retreats nine squads in twenty seconds, then five
  more at 17:26. Something on your side was winning there. Your follow-up
  production over the same window was a pioneer and a medical truck."*

**Calling out a weak player.**
- Bad: *"K0pF was useless and threw the game."*
- Good: *"K0pF5414+ at 16.6 commands per minute — 40% of his nearest teammate.
  Two produced squads in twenty-one minutes, three capture commands. A call-in
  battlegroup explains fewer buildings, not fewer actions."*

**Reporting an anomaly.**
- Bad: *"poker disconnected at 6:47."*
- Good: *"At 06:47 an AI-player event fires on poker's slot after a 60-second
  command gap, and his camera-event count is a quarter of everyone else's. That
  fits a brief drop, but the file doesn't say so outright."*

**Crossing the two layers** (this is where the coh3stats data earns its keep).
- Bad: *"DeathStyle carried the team — 57.7 CPM, most builds, most attacks."* —
  activity mistaken for impact.
- Good: *"DeathStyle was the busiest player on the map (57.7 CPM) and the least
  effective with it: 38 kills against 65 losses, 4 vehicles lost, and the lowest
  damage on his team (4,428). Meanwhile OstwindRush — who the input log makes
  look like a passenger at 21.9 CPM and 90% own-half — quietly had the team's
  best game by outcome: 101 kills for 37 losses. The wooden spoon goes on effort
  without results, not on a low command count."*

## Multiple replays

When several `.rec` files are available from the same group, run all of them and
look for what repeats. A single game's mistakes are noise; the same player
banking command points until minute 15 in three consecutive games is the finding
worth writing down. Cross-replay comparison is where this skill earns the most,
so ask whether more replays exist when the user is clearly reviewing their own
team rather than a one-off.
