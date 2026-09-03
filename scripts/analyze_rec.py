#!/usr/bin/env python3
"""
analyze_rec.py -- turn a CoH3 .rec into an evidence brief.

    python3 analyze_rec.py REPLAY.rec [--json out.json] [--no-lookup]

Prints every table needed to write a match analysis. It deliberately does NOT
write the analysis: the numbers are the input to your judgement, not a
substitute for it.

Everything printed is derived from recorded player input. Kills, losses,
victory points, successful captures and resource income are NOT in the file --
if you catch yourself about to write one, stop. A capture command is an order /
intent to capture a point, not proof that ownership actually changed.
"""

import argparse
import collections
import struct
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from coh3rec import (  # noqa: E402
    Replay, load_lookup, team_anchors, make_projector, anchor_quality, mmss,
    COMMAND_TYPES, NOISE_TYPES, BUILD_TYPES, RETREAT_TYPES, ATTACK_TYPES,
    CAPTURE_TYPES, RECREW_TYPES, ABILITY_TYPES, UPGRADE_TYPES,
    REINFORCE_TYPES, POSITIONAL_TYPES, BG_PURCHASE, TICKS_PER_SEC,
)

# Vehicles are identified by their blueprint CATEGORY (from the coh3-data
# path), never by name substrings -- "panzergrenadier" contains "panzer" but is
# infantry, and that mistake silently inflates one side's armour count.
# Within vehicles, these names mark a medium tank / tank destroyer / assault gun
# rather than a car or halftrack. The armour timeline is usually the single most
# explanatory table in the report, so it is worth getting the split right.
TANK_HINTS = (
    'stug', 'marder', 'panzer_iv', 'panzer_iii', 'tiger', 'panther', 'brummbar',
    'sherman', 'hellcat', 'jackson', 'wolverine', 'chaffee', 'pershing',
    'crusader', 'grant', 'matilda', 'valentine', 'archer', 'churchill',
    'centaur', 'cromwell', 'stuart', 'greyhound', 'puma', 'bishop', 'priest',
    'wespe', 'scott', 'nashorn', 'elefant', 'jagd',
)


def sec(title):
    print(f"\n{'=' * 78}\n{title}\n{'=' * 78}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('replay')
    ap.add_argument('--json', help='also write structured output here')
    ap.add_argument('--no-lookup', action='store_true',
                    help='skip blueprint names (fast; shows raw pbgids)')
    ap.add_argument('--cache', help='path to blueprint cache json')
    ap.add_argument('--block', type=int, default=3, help='timeline block size in minutes')
    ap.add_argument('--anchors', help="override estimated base positions: "
                                      "'axisX,axisZ:alliesX,alliesZ'")
    args = ap.parse_args()

    if args.block < 1:
        ap.error('--block must be at least 1 minute')

    r = Replay(args.replay)
    lookup = {}
    if not args.no_lookup:
        # A missing cache means a ~110 MB download; if that fails we still want
        # the whole brief, just with raw pbgids instead of names.
        try:
            lookup = load_lookup(cache=args.cache)
        except Exception as exc:
            print(f"WARNING: blueprint lookup unavailable ({exc}). "
                  f"Unit and ability names will show as raw pbgids, and the "
                  f"slot check and vehicle classification are skipped.",
                  file=sys.stderr)

    slots = sorted(r.players, key=lambda s: (r.players[s].side != 'AXIS', s))
    P = r.players
    dur_min = r.max_tick / TICKS_PER_SEC / 60 or 1

    sec('MATCH')
    print(f"file        {os.path.basename(args.replay)}")
    print(f"recorded    {r.timestamp}")
    print(f"map         {r.map}")
    print(f"duration    {r.duration}  ({r.max_tick} ticks)")
    sides = collections.Counter(p.side for p in P.values())
    print(f"format      {sides.get('AXIS',0)}v{sides.get('ALLIES',0)}")
    for s in slots:
        p = P[s]
        print(f"  slot {p.slot}  team {p.team}  {p.side:6s}  {p.faction:15s}  {p.name}")

    win, lose, tick = r.outcome()
    print()
    quitters = [(t, s) for t, s in r.surrenders() if s in P]
    if win:
        who = ', '.join(P[s].name for _, s in quitters)
        print(f"OUTCOME     {lose} conceded at {mmss(tick)} ({who}) -> {win} won")
    elif quitters:
        # Some players surrendered but not a whole side -- that is a partial
        # concede, not a team loss. Their team may still have won.
        who = ', '.join(f"{P[s].name} ({P[s].side}) at {mmss(t)}" for t, s in quitters)
        print(f"OUTCOME     partial concede only -- {who}. Not every player on a side "
              "surrendered, so the file does NOT state a winner. Do not guess.")
    else:
        print("OUTCOME     no surrender recorded. The file does not state a winner; "
              "the match ended by annihilation, VP depletion or a drop. Do not guess.")

    problems = r.verify_slots(lookup) if lookup else ['(skipped -- no blueprint lookup)']
    print(f"slot check  {'OK - build races match header factions' if not problems else problems}")

    acts = r.actions()

    sec('PER-PLAYER TOTALS   (CPM = non-camera commands per minute)')
    hdr = ('slot side   player          faction        cmds   CPM  camera build retr '
           'atk capord recrew abil upgr reinf BGbuy  last')
    print(hdr)
    rows = {}
    for s in slots:
        mine = [c for c in acts if c.slot == s]
        cam = sum(1 for c in r.commands if c.slot == s and c.type == 157)

        def n(types):
            return sum(1 for c in mine if c.type in types)
        # Last REAL action: r.commands still carries the type-158 heartbeat,
        # which runs to the end of the file for everyone and would hide a drop.
        last = max((c.tick for c in mine), default=0)
        row = dict(cmds=len(mine), cpm=round(len(mine) / dur_min, 1), camera=cam,
                   build=n(BUILD_TYPES), retreat=n(RETREAT_TYPES), attack=n(ATTACK_TYPES),
                   capture_orders=n(CAPTURE_TYPES), recrew=n(RECREW_TYPES),
                   ability=n(ABILITY_TYPES), upgrade=n(UPGRADE_TYPES),
                   reinforce=n(REINFORCE_TYPES), bg=n({BG_PURCHASE}), last=mmss(last))
        rows[s] = row
        p = P[s]
        print(f"{s:4d} {p.side:6s} {p.name[:15]:15s} {p.faction:14s} {row['cmds']:5d} "
              f"{row['cpm']:5.1f} {cam:6d} {row['build']:5d} {row['retreat']:4d} "
              f"{row['attack']:4d} {row['capture_orders']:6d} {row['recrew']:6d} "
              f"{row['ability']:4d} {row['upgrade']:4d} {row['reinforce']:5d} "
              f"{row['bg']:5d}  {row['last']}")

    print("\n  capord = capture ORDERS (intent only, not successful captures); "
          "recrew = team-weapon recrew/capture commands.")
    print("  Neither field is an end-game territory result. Use Relic/coh3stats "
          "counters for successful captures.\n")
    for side in ('AXIS', 'ALLIES'):
        ss = [s for s in slots if P[s].side == side]
        tot = lambda k: sum(rows[s][k] for s in ss)  # noqa: E731
        print(f"{side:6s} cmds={tot('cmds'):5d}  squads={tot('build'):3d}  "
              f"retreats={tot('retreat'):3d}  attacks={tot('attack'):3d}  "
              f"capture_orders={tot('capture_orders'):3d}  recrews={tot('recrew'):3d}  "
              f"reinforce={tot('reinforce'):3d}  BGbuys={tot('bg'):3d}")

    builds = r.builds(lookup)
    per_build = collections.defaultdict(list)
    for t, s, pb, nm in builds:
        per_build[s].append((t, nm))

    sec('BUILD ORDERS')
    for s in slots:
        p = P[s]
        print(f"\n-- {p.name} ({p.faction}, {p.side}) : {len(per_build[s])} squads")
        line = '   ' + '  |  '.join(f"{mmss(t)} {nm.split('/')[-1]}" for t, nm in per_build[s])
        print(line if per_build[s] else '   (none)')

    sec('PRODUCTION GAPS  (>150s between squads, plus dead time at the end)')
    for s in slots:
        ts = [t for t, _ in per_build[s]]
        gaps = [(ts[i + 1] - ts[i], ts[i], ts[i + 1]) for i in range(len(ts) - 1)
                if ts[i + 1] - ts[i] > 150 * TICKS_PER_SEC]
        tail = (r.max_tick - ts[-1]) / TICKS_PER_SEC / 60 if ts else 0
        g = '  '.join(f"{d / TICKS_PER_SEC / 60:.1f}min {mmss(a)}->{mmss(b)}" for d, a, b in gaps)
        print(f"{P[s].name[:15]:15s} {g:60s} last build {mmss(ts[-1]) if ts else '--':>5s} "
              f"({tail:.1f}min before end)")

    sec('SQUAD COMPOSITION  (by blueprint category)')
    comp = collections.defaultdict(collections.Counter)
    for t, s, pb, nm in builds:
        comp[s][(lookup.get(pb) or {}).get('category', 'unknown')] += 1
    cats = sorted({c for v in comp.values() for c in v})
    print(f"{'player':16s}" + ''.join(f"{c[:12]:>13s}" for c in cats))
    for s in slots:
        print(f"{P[s].name[:15]:16s}" + ''.join(f"{comp[s][c]:13d}" for c in cats))

    sec('VEHICLE TIMELINE  (category=vehicles; [T] = medium tank / TD / assault gun)')
    veh = [(t, s, nm, any(h in nm.lower() for h in TANK_HINTS))
           for t, s, pb, nm in builds
           if (lookup.get(pb) or {}).get('category') == 'vehicles']
    for t, s, nm, is_tank in sorted(veh):
        if s in P:
            print(f"  {mmss(t)}  {P[s].side:6s}  {'[T]' if is_tank else '   '} "
                  f"{P[s].name[:15]:15s} {nm.split('/')[-1]}")
    for side in ('AXIS', 'ALLIES'):
        tot = sum(1 for _, s, _, _ in veh if s in P and P[s].side == side)
        tanks = sum(1 for _, s, _, k in veh if s in P and P[s].side == side and k)
        print(f"  {side:6s} vehicles={tot:3d}  of which tanks/TDs={tanks:3d}")
    if not lookup:
        print("  (blueprint lookup disabled -- vehicle classification unavailable)")

    sec('RETREATS  (timeline, then bursts of >=3 within 30s)')
    for s in slots:
        ts = sorted(c.tick for c in r.commands if c.slot == s and c.type in RETREAT_TYPES)
        print(f"{P[s].name[:15]:15s} n={len(ts):3d}  {' '.join(mmss(t) for t in ts)}")
    print()
    for s in slots:
        ts = sorted(c.tick for c in r.commands if c.slot == s and c.type in RETREAT_TYPES)
        out, i = [], 0
        while i < len(ts):
            j = i
            while j + 1 < len(ts) and ts[j + 1] - ts[i] <= 30 * TICKS_PER_SEC:
                j += 1
            if j - i + 1 >= 3:
                out.append(f"{mmss(ts[i])}-{mmss(ts[j])} x{j - i + 1}")
            i = j + 1
        print(f"{P[s].name[:15]:15s} bursts: {'  '.join(out) if out else '-'}")

    B = args.block * 60 * TICKS_PER_SEC
    nblocks = int(r.max_tick // B) + 1

    def blocktable(title, pred):
        sec(title)
        print(f"{'player':16s}" + ''.join(f"{i * args.block:>7}" for i in range(nblocks)))
        for s in slots:
            counts = [0] * nblocks
            for c in r.commands:
                if c.slot == s and pred(c):
                    counts[min(int(c.tick // B), nblocks - 1)] += 1
            print(f"{P[s].name[:15]:16s}" + ''.join(f"{v:7d}" for v in counts))

    blocktable(f'ACTIVITY per {args.block}min (non-camera commands)',
               lambda c: c.type not in NOISE_TYPES)
    blocktable(f'ATTACK COMMANDS per {args.block}min', lambda c: c.type in ATTACK_TYPES)

    anchors, firsts = team_anchors(r)
    override = None
    if args.anchors:
        try:
            lhs, rhs = args.anchors.split(':')
            parsed = {'AXIS': tuple(float(v) for v in lhs.split(',')),
                      'ALLIES': tuple(float(v) for v in rhs.split(','))}
            # Arity must be checked here: make_projector unpacks these as
            # (x, z) far below, outside this guard.
            if any(len(v) != 2 for v in parsed.values()):
                raise ValueError('each side needs exactly two coordinates')
            anchors = parsed
            override = True
        except Exception:
            sys.exit("--anchors must look like '142,127:-130,-140'")
    depth, lateral = make_projector(anchors, 'AXIS')

    sec('TERRITORY  (depth 0 = Axis base, 100 = Allied base)')
    if depth is None:
        print("  could not establish base anchors -- too few positional commands")
    else:
        for side, xy in anchors.items():
            print(f"  {side} base anchor ~ ({xy[0]:.0f}, {xy[1]:.0f})"
                  + ("  [manual override]" if override else "  [estimated]"))
        print("  each player's first positional order (the raw evidence for the above):")
        for s in slots:
            if s in firsts:
                print(f"    {P[s].side:6s} {P[s].name[:15]:15s} "
                      f"({firsts[s][0]:7.0f}, {firsts[s][1]:7.0f})")
        if not override:
            ratio, centre, warn = anchor_quality(r, anchors)
            if centre:
                print(f"  playable-area centre ~ ({centre[0]:.0f}, {centre[1]:.0f}), "
                      f"anchor symmetry {ratio:.2f} (1.00 = ideal)")
            if warn:
                print(f"\n  ** ANCHOR WARNING ** {warn}")
        pos = collections.defaultdict(list)
        for c in r.commands:
            if c.slot in P and c.type in POSITIONAL_TYPES:
                xy = c.coords()
                if xy:
                    pos[c.slot].append((c.tick, depth(*xy), lateral(*xy)))

        print("\nLANE ASSIGNMENT  (players with similar lateral values contest the "
              "same corridor;\ntwo teammates within ~40 units of each other are stacked)")
        for s in sorted(slots, key=lambda s: -(sum(q[2] for q in pos[s]) / len(pos[s])
                                               if pos[s] else 0)):
            if not pos[s]:
                continue
            lat = sum(q[2] for q in pos[s]) / len(pos[s])
            dep = sum(q[1] for q in pos[s]) / len(pos[s])
            # "forward" is opposite for the two sides: Axis advances as depth
            # rises, Allies as it falls. Own-half must respect that.
            if P[s].side == 'AXIS':
                own = sum(1 for q in pos[s] if q[1] < 50)
            else:
                own = sum(1 for q in pos[s] if q[1] > 50)
            own = own / len(pos[s]) * 100
            print(f"  {P[s].name[:15]:15s} {P[s].side:6s} lateral={lat:7.0f} "
                  f"mean_depth={dep:5.0f}  own_half={own:3.0f}%  n={len(pos[s])}")

        print(f"\nMEAN DEPTH per {args.block}min block")
        print(f"{'player':16s}" + ''.join(f"{i * args.block:>7}" for i in range(nblocks)))
        for s in slots:
            row = ''
            for i in range(nblocks):
                v = [q[1] for q in pos[s] if i * B <= q[0] < (i + 1) * B]
                row += f"{sum(v) / len(v):7.0f}" if v else "      -"
            print(f"{P[s].name[:15]:16s}{row}")
        teamrows = {}
        for side in ('AXIS', 'ALLIES'):
            vals = []
            for i in range(nblocks):
                v = [q[1] for s in slots if P[s].side == side
                     for q in pos[s] if i * B <= q[0] < (i + 1) * B]
                vals.append(sum(v) / len(v) if v else None)
            teamrows[side] = vals
            print(f"{side + ' (team)':16s}" +
                  ''.join(f"{x:7.0f}" if x is not None else "      -" for x in vals))
        front = [((a + b) / 2) if (a is not None and b is not None) else None
                 for a, b in zip(teamrows['AXIS'], teamrows['ALLIES'])]
        print(f"{'FRONT LINE':16s}" +
              ''.join(f"{x:7.0f}" if x is not None else "      -" for x in front))
        print("\nRead FRONT LINE, not the raw team rows. Depth rises toward the Allied\n"
              "base, so 'forward' is the opposite direction for each side and the two team\n"
              "rows are not directly comparable. Their midpoint is where the fighting sits:\n"
              "  >50 = play is happening in Allied territory (Axis pushing)\n"
              "  <50 = play is happening in Axis territory (Axis pinned back)\n"
              "Absolute values depend on the estimated base anchors; the trend does not.")

    if lookup:
        sec('ABILITIES & CALL-INS  (resolved blueprint names)')
        for c in r.commands:
            if c.type in ABILITY_TYPES and c.slot in P:
                hits = {lookup[v]['name'] for v in c.scan_pbgids(lookup)}
                if hits:
                    print(f"  {mmss(c.tick)}  {P[c.slot].name[:15]:15s} {sorted(hits)}")

    sec('BATTLEGROUP PURCHASES  (PCMD_TentativeUpgradePurchaseAll = CP spent)')
    for s in slots:
        ts = [mmss(c.tick) for c in r.commands if c.slot == s and c.type == BG_PURCHASE]
        print(f"{P[s].name[:15]:15s} n={len(ts):2d}  {' '.join(ts)}")

    if r.chat:
        sec('CHAT')
        for t, who, msg in r.chat:
            print(f"  {mmss(t)}  {who}: {msg}")

    sec('ANOMALIES  (worth a look; meanings are not all confirmed)')
    for t, kind, detail in r.events:
        print(f"  {mmss(t)}  stream event {kind} {detail}")
    for c in r.commands:
        if c.type in (144, 145, 149, 150) and c.slot in P:
            print(f"  {mmss(c.tick)}  {P[c.slot].name}: {c.name}")
    cams = {s: rows[s]['camera'] for s in slots}
    if cams and max(cams.values()) > 3 * (min(cams.values()) or 1):
        lo = min(cams, key=cams.get)
        print(f"  camera-event outlier: {P[lo].name} {cams[lo]} vs max "
              f"{max(cams.values())} -- possible drop, spectator lag or a static-camera style")
    idle = []
    for s in slots:
        # Noise-filtered: the ~2s heartbeat (158) never stops, so scanning
        # r.commands here would make a 45s gap arithmetically impossible.
        ts = sorted(c.tick for c in acts if c.slot == s)
        for i in range(len(ts) - 1):
            if ts[i + 1] - ts[i] > 45 * TICKS_PER_SEC:
                idle.append((P[s].name, mmss(ts[i]), (ts[i + 1] - ts[i]) / TICKS_PER_SEC))
    for nm, at, d in idle:
        print(f"  {at}  {nm} issued no command for {d:.0f}s")

    sec('COMMAND TYPE HISTOGRAM')
    for k, v in sorted(collections.Counter(c.type for c in r.commands).items(),
                       key=lambda x: -x[1]):
        print(f"  {k:3d} {COMMAND_TYPES.get(k, '?'):40s} {v}")

    if args.json:
        import json
        blob = {
            'map': r.map, 'timestamp': r.timestamp, 'duration': r.duration,
            'ticks': r.max_tick,
            'players': [{'slot': p.slot, 'team': p.team, 'name': p.name,
                         'faction': p.faction, 'side': p.side, **rows[p.slot]}
                        for p in (P[s] for s in slots)],
            'outcome': {'winner': win, 'loser': lose,
                        'concede_at': mmss(tick) if tick else None},
            'slot_check': problems,
            'builds': [{'t': mmss(t), 'slot': s, 'unit': nm} for t, s, pb, nm in builds],
            'chat': [{'t': mmss(t), 'who': w, 'msg': m} for t, w, m in r.chat],
        }
        with open(args.json, 'w') as fh:
            json.dump(blob, fh, indent=2)
        print(f"\nwrote {args.json}")


if __name__ == '__main__':
    main()