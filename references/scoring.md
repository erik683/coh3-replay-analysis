# Outcome-first scoring and evidence hierarchy

This project has two fundamentally different evidence classes. Treating them as
interchangeable produces confident but wrong player rankings.

## The rule

**Outcomes score performance. Inputs diagnose process.**

Relic/coh3stats end-game counters are outcome evidence. Replay commands are
intent/process evidence. A command says what a player tried to do, not whether it
worked.

When outcome data exists, player-impact judgements, MVP/wooden-spoon calls, and
claims about who won or lost a lane MUST be led by outcome data. Replay metrics
may explain those results, but may not overrule them merely because the input
volume looks dramatic.

When outcome data does not exist, do not manufacture an overall performance
ranking from replay activity. Restrict the report to process observations and
state that combat-efficiency ranking is unavailable.

## Evidence hierarchy for player impact

Use this order of precedence:

1. **Combat outcomes**: model K/D, squad kills/losses, vehicle kills/losses,
   damage dealt. Squad and vehicle trades deserve more weight than raw model K/D
   because wipes and vehicle losses represent larger resource/tempo swings.
2. **Objective outcomes**: Relic `pcap`, recaptures/strategy-point outcomes when
   available, plus authoritative match result.
3. **Survival/economy proxies**: production/replacement burden, veterancy,
   resource-spend fields when available.
4. **Replay process evidence**: lane position, retreat bursts, vehicle timing,
   production gaps, ability timing, pressure windows.
5. **Raw activity**: CPM/APM, attack-command count, capture-command count.

Levels 4-5 explain *how* somebody played. They are not substitutes for levels
1-3.

## CPM / APM

CPM is a workload and interaction-density metric, not a performance score.

- High CPM can mean excellent multitasking, frantic recovery, inefficient
  clicking, or simply a micro-heavy army.
- Low CPM can mean poor involvement, a low-micro composition, deliberate play,
  or unusually efficient execution.
- A team-level activity gap is useful as a pressure/context signal, but it is
  **never sufficient by itself to explain a loss** when outcome data is
  available.
- Never label a player a passenger, carry, MVP, or worst player from CPM alone.
- Never add CPM to a composite player-impact score. If a score is needed, keep
  CPM as a separately reported diagnostic dimension.

The Steppes regression case is the canonical counterexample: a very low-input
Axis player still led his team in raw kills and vehicle kills, while a more
active teammate had substantially worse trade efficiency. Ranking them from CPM
alone reverses the outcome evidence.

## Capture commands

A replay capture command means only:

> "the player issued an order to capture this target."

It does **not** mean the point was captured, held, denied, or strategically
valuable. The order may be cancelled, interrupted, arrive after another unit,
or fail because the fight is lost.

Therefore:

- call the replay field **capture orders**, never captures;
- give capture orders **zero direct performance credit**;
- use Relic `pcap` / end-game strategy-point counters for successful captures;
- use territory/front-line movement to discuss map pressure;
- discuss the strategic value of a specific fuel/munition/VP only when the map
  evidence or human replay observation identifies it.

A high number of capture orders can support a narrow process statement such as
"frequently issued territory orders". It cannot support "best map player" by
itself.

## Retreats and attack commands

These are also input signatures, not outcomes.

- A retreat burst shows that many units were ordered home in a short window. It
  does not prove how many models were lost or which opponent caused it.
- Attack commands show combat interaction/pressure, not damage or victory.
- Repeated retreat bursts may explain poor end-game trades, but if the end-game
  trades are good, describe the player as successfully preserving units under
  pressure rather than automatically penalising the retreat count.

## Mandatory report gate

Before issuing an overall player ranking or causal verdict, answer these:

1. Was a coh3stats match URL/id supplied?
2. If yes, were Relic end-game counters successfully retrieved or supplied by
   the user?
3. If not, is the report explicitly labelled `.rec-only` and are MVP/worst-player
   / combat-efficiency conclusions withheld?
4. Are every replay `capture` value and timeline entry described as a capture
   **order**, not a successful capture?
5. If CPM conflicts with outcome efficiency, does the report follow the outcome
   evidence and use CPM only to explain the contrast?

If any answer is no, the report is not ready.

## Suggested outcome read

Do not force all factions and roles into one magic scalar. Prefer a compact
scorecard with several independent dimensions:

- **Model efficiency:** kills / deaths
- **Squad trade:** squads killed / squads lost
- **Vehicle trade:** vehicles killed / vehicles lost
- **Damage:** absolute and team share
- **Objectives:** successful captures / recaptures where available
- **Process:** CPM, retreat bursts, production timing, lane pressure

If a single MVP/wooden-spoon call is requested, decide from the outcome card
first. Use replay process evidence only as a tie-breaker or explanation.
