# CoH3 `.rec` binary format

Reverse-engineered against game build 2026-era replays. Command type ids match
the `vault` crate's `CommandType` enum (ryantaylor/vault), which covers CoH2 and
CoH3. Everything is little-endian. Read this when `analyze_rec.py` throws, when
a new patch shifts an offset, or when you need a field the parser doesn't expose.

## Contents

- [File layout](#file-layout)
- [Relic Chunky containers](#relic-chunky-containers)
- [Player records](#player-records)
- [Scenario chunk](#scenario-chunk)
- [Command stream](#command-stream)
- [Action payloads](#action-payloads)
- [Blueprint ids](#blueprint-ids)
- [Failure modes](#failure-modes)

## File layout

| offset | bytes | meaning |
|---|---|---|
| 0 | 4 | version-ish word, observed `00 00 98 bf` |
| 4 | 8 | magic `COH3_RE\0` |
| 12 | var | UTF-16LE local timestamp, null-padded |
| 76 | — | first Relic Chunky (`FOLDPOST` / `DATADATA`) |
| — | — | second Relic Chunky (`FOLDINFO` + `DATASDSC`) |
| — | EOF | command stream |

The timestamp is whatever the recording client's locale produced
(`23.08.2026 23:51`, `8/23/2026 5:24 PM`) — don't try to parse it into a
datetime, just display it.

The command stream starts immediately after the second chunky ends, and runs to
EOF with no padding. A clean parse consumes the file exactly; if your walk stops
short, the tick loop desynced.

## Relic Chunky containers

Header: `Relic Chunky`, then `\r\n\x1a\x00`, then u32 version, u32 platform.
Then a sequence of chunks:

| field | size |
|---|---|
| type | 4 bytes, `FOLD` or `DATA` |
| name | 4 bytes, e.g. `INFO`, `DATA`, `SDSC` |
| version | u32 |
| size | u32 (bytes of chunk data) |
| name length | u32 |
| name | *name length* bytes |
| data | *size* bytes |

`FOLD*` chunks contain nested chunks; `DATA*` chunks are leaves. Chunks seen:
`FOLDPOST/DATADATA`, `FOLDINFO/{DATADATA, DATAPLAS, DATAGRIF, DATASAVP,
DATAMTYP, DATAREPL, DATALOCS, DATAAUTO}`, `DATASDSC`.

The player table lives in `FOLDINFO`'s `DATADATA`. The map/scenario lives in
`DATASDSC`.

`FOLDPOST`'s `DATADATA` is a single 4-byte chunk holding a u32: the **final tick
count**. Across 23 replays tested it equals the maximum tick in the command
stream exactly, so it is a header-level match-length value and a cheap
end-of-stream cross-check — if your walk finishes on a different tick, it
desynced. The parser still derives `duration` from the max observed tick; this
chunk is the independent confirmation.

## Player records

Inside `FOLDINFO/DATADATA`, each player is:

```
01 <u32 namelen> <UTF-16LE name, namelen chars>
<u32 team> <u32 slot>
01 <u32 faclen> <ASCII faction, faclen bytes>
```

Factions: `afrika_korps`, `germans` (Axis) and `british_africa`, `americans`
(Allies). After the faction come cosmetic/loadout blobs — skip to the next `01`
length-prefix pattern.

Three things that will bite you:

1. **Header order is not slot order.** In one observed 3v3 the header order was
   slots 1,4,3,2,5,0. The `slot` field is what appears in the command stream.
2. **Names contain non-ASCII.** Observed: a leading `➡` (U+27A1) and `桂`
   (U+6842). Scanning for runs of ASCII-in-UTF-16 silently truncates or drops
   these players. Walk the record structure instead.
3. **`team` is an arbitrary 0/1 label, not a side.** In one replay Axis was
   team 0; in another, team 1. Derive the side from the faction.

Verify the mapping by cross-referencing each slot's `CMD_BuildSquad` blueprints
against its header faction (`Replay.verify_slots`). A slot building
`grenadier_ger` is not the American player.

## Scenario chunk

`DATASDSC` holds the scenario path (`data:scenarios\multiplayer\<map>\<map>`)
plus a table of capture points. Each point entry is a comma-joined type string
(`victory_point,territory_point`, `resource_point,territory_point,resource_point_fuel,fuel_point_low`,
…) followed by `ff ff ff ff 00` and two floats: world x and z.

Point extraction is the least reliable part of the parser — the same VP appears
in more than one table with different alignments and some reads come back as
obvious garbage. Treat the coordinates as a hint, not ground truth, and prefer
deriving geography from command coordinates.

## Command stream

A flat sequence of chunks: u32 type, u32 size, then *size* bytes of body.

**type 0 — simulation tick**

```
u8   0x20
u32  tick index          (8 ticks per second)
u32  hash / seed
u32  action count
     then action_count action records
```

An idle tick is 13 bytes with action count 0. Duration = max tick / 8.

**type 1 — out-of-band event**

```
u32  subtype
u32  remaining size
```

- subtype 1 = chat. Then u32, u32, u32, then at offset 20: u32 name length,
  UTF-16LE name, u32 message length, UTF-16LE message.
- subtype 0 = player state event; payload at offset 8 is a player entity id
  (1000 + slot). Observed once alongside `PCMD_AIPlayer`, consistent with a
  disconnect or AI handover, but unconfirmed.

**You must skip type-1 chunks in the tick loop.** Parsing one as a tick throws
a struct error at best and produces garbage commands at worst.

## Action payloads

Each action record inside a type-0 tick:

```
u32  action index (global counter)
u32  zero
u32  payload length
     payload
```

Payload layout:

| offset | meaning |
|---|---|
| 0 | u8 payload length (repeats the field above) |
| 1 | u8, observed 0 |
| 2 | **u8 command type** — see `COMMAND_TYPES` in `scripts/coh3rec.py` |
| 3 | **u8 player slot** |
| … | subtype-specific |
| last 12 | for positional commands: 3 floats, x / y(height) / z |

Two additional constants recur: a u32 `256 + slot` and a u32 `1000 + slot`
(the player entity id). The latter is a useful cross-check on byte 3.

Coordinates are a property of *positional* commands only, not of every command,
and even among the positional types the trailing floats are not always a usable
map position. `Command.coords()` decodes the last 12 bytes and then applies a
plausibility gate (`|x|,|z| < 600`, `-80 < y < 300`, not at the origin); on a
tested 4v4 about 72% of `POSITIONAL_TYPES` commands and 24% of all commands pass
it. So the territory/lane math runs on roughly three-quarters of the positional
orders, which is why every per-player depth figure prints its sample size `n`.
Don't read a coordinate off a non-positional command's tail — it is other fields.

**`CMD_BuildSquad` (type 3):** u32 blueprint id at payload offset 35, u32 player
entity at 39.

**Ability / upgrade commands:** field offsets vary by subtype. Rather than
hardcoding them, slide a u32 window across the payload and keep values that
exist in the blueprint table (`Command.scan_pbgids`). This is how ability names
get resolved and it works well in practice.

**Types 157 and 158 are not player actions.** 157 is camera movement — high
volume, and a useful proxy for screen activity. 158 fires a near-identical
number of times for every player (roughly one per 16 ticks), which is what
identifies it as a sync heartbeat rather than input. Excluding both is what
makes CPM meaningful.

Semantically useful types: 3 build, 62 move, 66 capture, 67 attack, 68
reinforce, 69/16 upgrade, 71 attack-move, 72/14/132 ability, 73/76 load/unload,
78 retreat, 79/100 team-weapon capture / recrew, 128 place structure,
138 battlegroup purchase, 144/150 AI-player events, 146 surrender,
148 broadcast.

## Blueprint ids

Names come from `github.com/cohstats/coh3-data` (`master/data/`):

| file | size | contents |
|---|---|---|
| `sbps.json` | ~48 MB | squad blueprints — units |
| `abilities.json` | ~61 MB | abilities, call-ins, off-map |
| `battlegroup.json` | ~150 KB | battlegroup trees |
| `ebps.json` | ~93 MB | entity blueprints — buildings, emplacements |

Walk for any object carrying a `pbgid` key; the key chain gives race, category
and name (`races/german/vehicles/stug_iii_ger`). `ebps` is skipped by default —
large and rarely needed. `sbps.json` also has a non-`races` top-level section
(campaign content) whose entries are harmless but shouldn't be treated as
multiplayer units.

**Classify units by the `category` element of the path**, never by name
substring. `panzergrenadier` contains `panzer` and is infantry.

If the repo layout moves, search for the current release rather than assuming
these paths still resolve.

## Failure modes

| symptom | cause |
|---|---|
| `struct.error` in the tick loop | a type-1 chunk parsed as a tick |
| stream walk ends before EOF | desync — re-check chunk sizes |
| a player missing from the roster | non-ASCII name, or a record scan that assumed ASCII |
| per-player stats attributed to the wrong person | header order used instead of the slot field |
| every unit shows as `pbgid:NNNNNN` | blueprint cache missing or download failed |
| infantry counted as armour | name-substring classification |
| both teams look like they're winning territory | depth compared without accounting for opposite forward directions |
| depth numbers all bunched near midfield | a base anchor poisoned by a player whose first order was already forward |
| anchor-symmetry ratio below 0.85 | same cause; re-run with `--anchors 'axX,axZ:alX,alZ'` using the well-clustered side's corner and its mirror |
