# coh3-replay-analysis — handoff bundle

Tools to decode and analyse **Company of Heroes 3 replay files (`.rec`)**. The
format is undocumented; this is reverse-engineered and validated against four
real multiplayer replays (3v3 and 4v4, two maps each).

Two ways to use it:

- **As a Claude Skill** — install `coh3-replay-analysis.skill`. `SKILL.md` is
  then loaded automatically when a `.rec` file shows up.
- **As plain scripts** — any agent or human can run `scripts/analyze_rec.py`
  directly. Python 3.8+, standard library only. No install step.

## Contents

```
SKILL.md                      workflow, how to read every table, report template
scripts/coh3rec.py            parser library (container, header, tick stream, geometry)
scripts/analyze_rec.py        CLI → full evidence brief
scripts/coh3_pbgid_cache.json pre-built blueprint id → unit name table (3,064 ids)
references/rec-format.md      byte-level format spec + failure-mode table
evals/evals.json              three test prompts with expected outputs
```

## Run it

```bash
python3 scripts/analyze_rec.py /path/to/replay.rec
python3 scripts/analyze_rec.py replay.rec --json out.json     # structured too
python3 scripts/analyze_rec.py replay.rec --no-lookup         # instant, raw pbgids
python3 scripts/analyze_rec.py replay.rec --block 2           # finer timeline
python3 scripts/analyze_rec.py replay.rec --anchors '142,127:-130,-140'
```

`coh3_pbgid_cache.json` ships with the bundle so unit names resolve **offline**.
The script looks for it in the working directory first, then
`~/.cache/coh3-rec/pbgid.json`; run from the bundle root, or pass `--cache`. If
it's missing the script rebuilds it from `github.com/cohstats/coh3-data`
(~110 MB download, about 6 seconds) — and still works without it, just with raw
`pbgid:198340` instead of `panzergrenadier_ak`.

Library use:

```python
import sys; sys.path.insert(0, 'scripts')
from coh3rec import Replay, load_lookup, team_anchors, make_projector, mmss
r = Replay('game.rec')
r.players            # {slot: Player(name, faction, side, team)}
r.duration, r.map, r.chat, r.outcome()
[c for c in r.commands if c.type == 78]     # every retreat, with tick + payload
r.builds(load_lookup())                     # [(tick, slot, pbgid, unit_name)]
```

## The one thing to internalise

**A `.rec` is an input log, not a stats dump.** It has every command with
timestamps and coordinates. It has **no** kills, losses, damage, veterancy,
victory-point tickers, resource income, or unit health — none of that exists
until the engine re-simulates the match.

So "he retreated nine squads in twenty seconds" is a fact from the file. "He
lost his Panzergrenadiers to a flank" is fiction. Describe fights by their
*input signature* — retreat bursts, ability spikes, production responses,
territory swings — and let the reader infer the rest. Users will ask for kill
counts; tell them the format doesn't carry them.

## Three traps that produce confidently wrong output

Each of these was hit during development and each is guarded in the code, but an
agent extending the parser should know them:

1. **Header order ≠ slot order.** Player records are not stored in slot order,
   and the `slot` field is what the command stream uses. Get it wrong and every
   per-player judgement lands on the wrong human. `Replay.verify_slots()`
   cross-checks each slot's built units against its header faction; the CLI
   prints the result as `slot check`. Never publish if it reports a mismatch.

2. **`team` is an arbitrary 0/1 label, not a side.** Axis was team 1 in one test
   replay and team 0 in another. Side is derived from faction
   (`afrika_korps`/`germans` = Axis).

3. **Base anchors are estimated and can be poisoned.** A player whose first
   order is already at midfield drags his side's anchor inward and inflates
   every depth number. The CLI prints an anchor-symmetry ratio and warns below
   0.85; resolve the warning with `--anchors` before quoting depth figures. The
   trend stays valid even when magnitudes are off.

Also: classify units by blueprint **category**, never name substring —
`panzergrenadier` contains `panzer` and is infantry. And depth runs 0→100 from
Axis base to Allied base, so "forward" is the opposite direction for each side;
read the `FRONT LINE` midpoint row, not the two team rows against each other.

Command types 157 (camera) and 158 (a ~2s per-player sync heartbeat) are engine
noise and are excluded from all activity counts.

## Validation status

Verified end to end against four replays:

| map | format | duration | outcome detected |
|---|---|---|---|
| `industrial_railyard_6p_mkii` | 3v3 | 16:12 | Allies conceded 16:06 |
| `monte_cavo_8p` | 4v4 | 21:03 | Axis conceded 20:55 |
| `powderkeg_8p` | 4v4 | 27:30 | Axis conceded 27:25 |
| `primosole_6p` | 3v3 | 22:57 | no surrender — winner not recorded |

All four parse to EOF with the slot check passing. The last one is the important
case: **a concede is the only outcome the file states directly.** If no surrender
is recorded the match ended by annihilation or VP depletion and the file does not
say who won. Say so; do not infer it from who looked stronger.

`references/rec-format.md` has the byte-level spec if a game patch shifts an
offset.
