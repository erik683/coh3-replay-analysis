---
name: coh3-replay-analysis
description: Analyse a Company of Heroes 3 match and write a coaching-style report. Fuse two evidence layers: coh3stats.com / Relic end-game counters describe what happened (kills, losses, damage, vehicle/squad trades, successful captures, authoritative result), while the replay (.rec) describes how players acted (build orders, retreats, abilities, command activity, territory/lane inputs). Preferred entry point is a coh3stats match URL or id. A loose .rec or post-game screenshot is a fallback. Use this skill whenever someone links a coh3stats match, uploads a CoH3 replay, asks why a team lost, requests a player breakdown, MVP/worst-player call, build-order review, or other replay analysis. The replay format is undocumented and command volume is not performance, so always parse and preserve the evidence hierarchy rather than guessing.
---

# CoH3 replay analysis

A `.rec` is Relic's deterministic **input log**. It records commands with tick
timestamps and, where applicable, world coordinates. The engine recreates the
match from those inputs.

That means the replay records **intent/process**, not simulated combat outcomes.

## Two evidence layers

### Relic / coh3stats = WHAT happened

Use end-game counters for:

- model kills/deaths (`ekills`, `edeaths`)
- squad kills/losses (`sqkill`, `sqlost`)
- vehicle kills/losses/abandons (`vkill`, `vlost`, `vabnd`)
- damage (`dmgdone`)
- successful strategy-point captures (`pcap`) and other outcome counters
- final veterancy
- authoritative win/loss

### `.rec` = HOW they played

The replay contains:

- roster, factions, teams, slots, map, duration
- build orders and production timing
- retreat orders and retreat bursts
- attack / move / ability / upgrade commands
- battlegroup purchases
- positional orders, territory depth and lane structure
- chat and surrender events

The replay does **not** contain kills, losses, damage, unit health, resource
income, successful point captures, or who actually won an individual fight.

So:

- Good: `DeathStyle issued six retreat orders in fourteen seconds.`
- Bad: `DeathStyle lost six squads in that fight.`

The first is recorded input. The second requires outcome/simulation evidence.

## Mandatory source-selection gate

**If the user supplies a coh3stats match URL or match id, the Relic/coh3stats
end-game layer is mandatory for any overall performance ranking or causal
verdict.** Do not silently fall back to `.rec`-only analysis just because a
replay file is also available.

Preferred command:

```bash
python3 scripts/coh3stats.py match <coh3stats-match-URL-or-id>
```

This fetches the end-game counters and then runs the replay analysis when the
replay is available.

If the API is temporarily unavailable but the user supplied the match URL:

1. still parse the replay for process/timeline observations;
2. label the result **`.rec-only / outcome counters unavailable`**;
3. **withhold MVP, wooden-spoon, carry/passenger, combat-efficiency, and strong
   player-ranking conclusions** until the end-game counters are recovered or
   supplied by the user;
4. ask for/pull the post-game table rather than substituting CPM for outcomes.

If the match is a custom lobby and has no coh3stats record, a supplied screenshot
of the post-game table can be used as screen-reported outcome evidence.

Useful flags:

- `--rec <file>` — use a local replay instead of downloading
- `--no-replay` — stats only
- `--anchor <profile_id>` — override the anchor
- `--json <out>` — save raw match JSON

The default anchor is **DeathStyle (#1101261)**. The friend group may be a 2–4
stack with random teammates; never assume a fixed roster.

## Replay-only workflow

For a loose replay with no tracked match:

```bash
python3 scripts/analyze_rec.py /path/to/replay.rec
```

Useful flags:

- `--json out.json`
- `--no-lookup`
- `--block N`
- `--cache PATH`
- `--anchors 'axisX,axisZ:alliesX,alliesZ'`

`references/rec-format.md` documents the byte-level format.
`references/coh3stats-api.md` documents the end-game API.
`references/scoring.md` defines the evidence hierarchy and scoring guardrails.

## Checks before writing

### 1. Verify slot mapping

The header is not stored in slot order. The slot field is authoritative for the
command stream. `analyze_rec.py` prints `slot check`; if it reports a mismatch,
stop and investigate rather than publishing player-specific claims.

### 2. Verify the outcome

When coh3stats is available, Relic's result is authoritative.

With a bare replay, the only directly recorded team result is a full-side
`PCMD_Surrender`. A partial concede is not a team result. If no full-side
surrender exists, say the replay does not state the winner.

### 3. Verify evidence completeness

Before an MVP/worst-player or strong causal diagnosis, confirm that outcome
counters are present. If they are missing, the report is process-only.

### 4. Verify territory anchors

If the territory anchor-quality warning fires, resolve it before quoting depth
magnitudes. A forward opening order can drag an estimated base anchor inward and
inflate depth values.

## Outcome-first scoring

The central rule is:

> **Outcomes score performance. Inputs diagnose process.**

Never build an overall player-impact ranking from replay command volume.

Use this order of precedence:

1. combat outcomes: squad/vehicle trades, model K/D, damage;
2. successful objective outcomes: Relic captures/recaptures and result;
3. survival/economy outcomes and veterancy when available;
4. replay process evidence: lane pressure, retreat bursts, armour timing,
   production gaps, ability timing;
5. raw activity: CPM/APM, attack orders, capture orders.

Levels 4–5 explain the result. They do not substitute for levels 1–3.

Prefer a multi-dimensional scorecard rather than one magic scalar:

- model efficiency = kills / deaths
- squad trade = squads killed / squads lost
- vehicle trade = vehicles killed / vehicles lost
- damage and team damage share
- successful objectives
- process context (CPM, retreats, timings, lane pressure)

If the user explicitly requests one MVP or wooden-spoon verdict, choose from the
outcome card first and use replay process evidence as a tie-breaker/explanation.

## CPM / APM: workload, not impact

CPM excludes camera and sync-heartbeat noise and is useful for measuring
interaction density. It is **not a performance score**.

High CPM can mean:

- excellent multitasking;
- inefficient clicking;
- frantic recovery while losing;
- a micro-heavy army composition.

Low CPM can mean:

- poor involvement;
- deliberate/efficient execution;
- a lower-micro composition;
- fewer simultaneous responsibilities.

Therefore:

- do not call a low-CPM player a `passenger` without outcome corroboration;
- do not call a high-CPM player a `carry` without outcome corroboration;
- do not add CPM directly to an overall player score;
- a 2× team command gap is a **pressure/context signal**, never by itself a
  sufficient explanation for a loss when outcome evidence exists;
- when CPM conflicts with actual trades/damage, follow the outcome evidence and
  highlight the contrast.

The Steppes regression case is the canonical example: a very low-input Axis
player led his team in raw kills and vehicle kills, while a more active teammate
had substantially worse trade efficiency. Ranking from CPM alone reverses the
actual results.

## Capture orders are intent, not success

Replay `capture_orders` / printed `capord` values are **capture orders** only.

A right-click/order on a VP, fuel, munition or territory point means the player
wanted a unit to capture it. It does not prove the capture completed, the point
was held, or the action had strategic value.

Always:

- say **capture orders**, never captures, when quoting the `.rec` field;
- give capture orders **zero direct performance credit**;
- use Relic `pcap` / end-game objective counters for successful captures;
- use territory/front-line movement for map-pressure analysis;
- distinguish raw point count from the strategic importance of a specific fuel,
  munition or VP;
- keep `recrew` separate: those are team-weapon recrew/capture commands, not
  territory recaptures.

A high capture-order count can support only a narrow process statement such as
`frequently issued territory orders`.

## Attack and retreat commands are also process evidence

Attack-command totals show interaction/pressure, not damage or fight wins.

Retreat bursts (for example, ≥3 retreat orders inside 30 seconds) identify
moments where many units were ordered home. Retreating may be good preservation,
not failure. Use end-game losses/trades to determine whether the player actually
bled units.

Good cross-layer reasoning:

- `Repeated retreat bursts after 25:00 coincide with poor squad/vehicle trades.`
- `Despite frequent retreats, the player finished positive in squad trade, so
  the retreats appear to have preserved the army rather than fed it.`

Bad reasoning:

- `He retreated 40 times, therefore he lost his lane.`

## Build orders and production gaps

Gaps over roughly 2.5 minutes and a late last conventional build can flag macro
issues, but check battlegroup call-ins and tech choices before calling the gap a
mistake. Low conventional production can be intentional; low outcome efficiency
is a separate question.

## Vehicle timeline

Vehicle classification comes from blueprint category, not name substring.
Focus on **timing**: when light vehicles, tanks, TDs and assault guns appear and
whether the opponent's armour cluster arrives before an answer is fielded.

When end-game stats are present, pair timing with actual vehicle trades instead
of inferring effectiveness from build count alone.

## Territory and lanes

Depth runs from Axis base toward Allied base. The two side rows are not directly
comparable; use the `FRONT LINE` midpoint/trend.

Lane assignment uses lateral offset from the base-to-base axis. Teammates stacked
within the same corridor while another flank is isolated can be a genuine team
structure problem, but avoid claiming a lane was won/lost solely from command
positions when combat outcomes are available.

## Anomalies

`PCMD_AIPlayer` events, long real-command gaps and outlier camera-event counts
can indicate a disconnect or AI handover. Report these as possible, not certain.

## Writing the report

Default structure:

1. Match header — map, mode, duration, roster, authoritative result if known.
2. Evidence note — state whether both outcome + replay layers are present.
3. **Outcome diagnosis first** — damage, squad/vehicle trades, successful
   objectives, major efficiency disparities.
4. Process explanation — CPM/context, production timing, armour timing, lanes,
   retreat/ability signatures.
5. Deciding windows — timestamped replay input signatures, carefully separated
   from end-game outcome totals.
6. Repeated issues — recurring patterns, especially across multiple replays.
7. Per-player breakdown — strengths first, then criticism, both evidence-backed.
8. MVP / wooden spoon only when outcome evidence is sufficient.

Every claim should trace to a table or recorded event. If you cannot point at the
evidence class, cut the line.

## Worked examples

### Activity versus impact

Bad:

`K0pF was useless: 16 CPM, hardly any capture orders.`

Good:

`K0pF operated at very low command tempo, but the end-game outcomes show high
impact: team-leading raw kills and vehicle kills. The real criticism is his high
replacement burden, not inactivity.`

### Capture orders

Bad:

`DeathStyle had 47 captures, best map player.`

Good:

`DeathStyle issued 47 capture orders in the replay. Relic's end-game table must
be used to determine how many strategy points were actually captured.`

### Retreats

Bad:

`Six retreats at 37:34 means six squads were lost.`

Good:

`Six retreat orders landed between 37:34 and 37:48, marking a major disengagement
window. Whether that represented effective preservation or a losing exchange is
judged from end-game losses/trades, not the retreat count itself.`

### Cross-layer contradiction

When the layers disagree, the disagreement is usually the insight:

`Player A had the highest CPM but poor squad/vehicle trades; Player B had low CPM
but positive trades and strong damage. A was busier, B was more effective.`

Never resolve that contradiction by treating activity as hidden performance.

## Multiple replays

Across several matches, look for repeated outcome/process relationships rather
than repeated raw APM alone. Examples:

- consistently high squad losses despite high damage;
- repeated vehicle-trade deficits after a specific tech timing;
- frequent capture orders but low successful objective outcomes;
- persistently low CPM **and** low damage/trades/map outcomes.

A single game's command count is noisy. Repeated outcome-backed patterns are the
coaching finding worth keeping.
