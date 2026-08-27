"""
coh3rec.py -- parser for Company of Heroes 3 replay (.rec) files.

A .rec is an INPUT LOG, not a stats dump. It contains every command every
player issued, with timestamps and (for positional commands) world
coordinates. It does NOT contain kills, losses, victory-point tickers,
resource income, or unit survival -- those only exist when the game engine
re-simulates the match. Never invent them.

See ../references/rec-format.md for the byte-level format notes.
"""

import collections
import json
import math
import os
import struct

TICKS_PER_SEC = 8

# Command type enum (Relic DCMD/SCMD/PCMD/CMD ids). Matches the `vault` crate's
# CommandType. 157 = camera movement, 158 = a ~2s per-player sync heartbeat --
# both are engine noise, not player actions. Exclude them from activity counts.
COMMAND_TYPES = {
    0: 'CMD_DefaultAction', 1: 'CMD_Stop', 2: 'CMD_Destroy', 3: 'CMD_BuildSquad',
    4: 'CMD_InstantBuildSquad', 5: 'CMD_CancelProduction', 6: 'CMD_BuildStructure',
    7: 'CMD_Move', 8: 'CMD_FlightMove', 9: 'CMD_Face', 10: 'CMD_Attack',
    11: 'CMD_AttackMove', 12: 'CMD_RallyPoint', 13: 'CMD_Capture', 14: 'CMD_Ability',
    15: 'CMD_Evacuate', 16: 'CMD_Upgrade', 17: 'CMD_InstantUpgrade', 18: 'CMD_Load',
    19: 'CMD_Unload', 20: 'CMD_UnloadSquads', 21: 'CMD_AttackStop', 22: 'CMD_AttackForced',
    23: 'CMD_SetHoldHeading', 24: 'CMD_StopMove', 25: 'CMD_Paradrop', 26: 'CMD_DefuseMine',
    27: 'CMD_Casualty', 28: 'CMD_Death', 29: 'CMD_InstantDeath', 30: 'CMD_Projectile',
    31: 'CMD_PlaceCharge', 32: 'CMD_BuildEntity', 33: 'CMD_RescueCasualty',
    34: 'CMD_AttackFromHold', 35: 'CMD_Vault', 36: 'CMD_KnockedBack', 37: 'CMD_Teardown',
    38: 'CMD_Melee', 39: 'CMD_ResolveOverlap', 40: 'CMD_Stun',
    41: 'CMD_InstantSetupTeamWeapon', 42: 'CMD_SetupTeamWeapon', 43: 'CMD_MoveToCover',
    44: 'CMD_Taunted', 45: 'CMD_Trade', 46: 'CMD_Brace', 47: 'CMD_Gather',
    48: 'CMD_PickUpSimItem', 49: 'CMD_ChangeCombatSlot', 50: 'CMD_RetreatMove',
    51: 'CMD_StopAbility', 52: 'CMD_InstantLoad', 53: 'CMD_RestoreWreck',
    54: 'CMD_Disable', 55: 'CMD_Enable', 56: 'CMD_CancelConstruction',
    57: 'CMD_HoldPositionOn', 58: 'CMD_HoldPositionOff', 59: 'CMD_CancelRestoreWreck',
    60: 'CMD_Repair', 61: 'CMD_COUNT',
    62: 'SCMD_Move', 63: 'SCMD_Stop', 64: 'SCMD_Destroy', 65: 'SCMD_BuildStructure',
    66: 'SCMD_Capture', 67: 'SCMD_Attack', 68: 'SCMD_ReinforceUnit', 69: 'SCMD_Upgrade',
    70: 'SCMD_CancelProduction', 71: 'SCMD_AttackMove', 72: 'SCMD_Ability',
    73: 'SCMD_Load', 74: 'SCMD_InstantLoad', 75: 'SCMD_UnloadSquads', 76: 'SCMD_Unload',
    77: 'SCMD_PickupTrailer', 78: 'SCMD_Retreat', 79: 'SCMD_CaptureTeamWeapon',
    80: 'SCMD_SetMoveType', 81: 'SCMD_InstantReinforceUnit', 82: 'SCMD_InstantUpgrade',
    83: 'SCMD_PlaceCharge', 84: 'SCMD_DefuseCharge', 85: 'SCMD_DropTrailer',
    86: 'SCMD_PickUpSimItem', 87: 'SCMD_DefuseMine', 88: 'SCMD_DoPlan', 89: 'SCMD_Patrol',
    90: 'SCMD_Surprise', 91: 'SCMD_InstantSetupTeamWeapon', 92: 'SCMD_SetupTeamWeapon',
    93: 'SCMD_AbandonTeamWeapon', 94: 'SCMD_StationaryAttack', 95: 'SCMD_RevertFieldSupport',
    96: 'SCMD_Face', 97: 'SCMD_BuildSquad', 98: 'SCMD_RallyPoint', 99: 'SCMD_RescueCasualty',
    100: 'SCMD_Recrew', 101: 'SCMD_Merge', 102: 'SCMD_WeaponPreference',
    103: 'SCMD_CombatStance', 104: 'SCMD_MoveToCover', 105: 'SCMD_Gather',
    106: 'SCMD_AttackWithinLeashArea', 107: 'SCMD_JoinFormationSquadGroup',
    108: 'SCMD_Trade', 109: 'SCMD_HoldPosition', 110: 'SCMD_Evacuate', 111: 'SCMD_Vault',
    112: 'SCMD_CancelQueuedCommand', 113: 'SCMD_RespondToBeingBreached',
    114: 'SCMD_StopAbility', 115: 'SCMD_InstantParadropReinforceUnit',
    116: 'SCMD_MoveUntilInsidePlayableArea', 117: 'SCMD_BeingTowed',
    118: 'SCMD_AttachingTrailer', 119: 'SCMD_DetachingTrailer', 120: 'SCMD_RestoreWreck',
    121: 'SCMD_AnimatedSpawn', 122: 'SCMD_COUNT',
    123: 'FCMD_FormationSquadGroupMove', 124: 'FCMD_FormationSquadGroupAttack',
    125: 'FCMD_FormationSquadGroupAttackMove', 126: 'FCMD_FormationSquadGroupStop',
    127: 'FCMD_COUNT',
    128: 'PCMD_PlaceAndConstructEntities', 129: 'PCMD_ResourceDonation',
    130: 'PCMD_CheatResources', 131: 'PCMD_CheatRevealAll', 132: 'PCMD_Ability',
    133: 'PCMD_CheatBuildTime', 134: 'PCMD_CheatIgnoreCosts', 135: 'PCMD_Upgrade',
    136: 'PCMD_InstantUpgrade', 137: 'PCMD_TentativeUpgrade',
    138: 'PCMD_TentativeUpgradePurchaseAll', 139: 'PCMD_UpgradeRemove',
    140: 'PCMD_TentativeUpgradeRemoveAll', 141: 'PCMD_SlotItemRemove',
    142: 'PCMD_CancelProduction', 143: 'PCMD_DetonateCharges', 144: 'PCMD_AIPlayer',
    145: 'PCMD_AIPlayer_EncounterNotification', 146: 'PCMD_Surrender',
    147: 'PCMD_WaitObjectDone', 148: 'PCMD_BroadcastMessage',
    149: 'PCMD_AIPlayer_EncounterSniped', 150: 'PCMD_AIPlayer_ResourceBonus',
    151: 'PCMD_FormationSquadGroupCreateBegin', 152: 'PCMD_FormationSquadGroupAddSquad',
    153: 'PCMD_FormationSquadGroupCreateEnd', 154: 'PCMD_EndTurn', 155: 'PCMD_StopAbility',
    156: 'PCMD_COUNT', 157: 'DCMD_CameraTrack', 158: 'DCMD_COUNT',
}

NOISE_TYPES = {157, 158}          # camera + sync heartbeat
FACTIONS = {'afrika_korps', 'germans', 'british_africa', 'americans'}
AXIS_FACTIONS = {'afrika_korps', 'germans'}

# Semantic groupings used by the analysis layer.
BUILD_TYPES = {3, 4, 97}
RETREAT_TYPES = {78, 50}
ATTACK_TYPES = {10, 11, 67, 71, 94}
CAPTURE_TYPES = {13, 66}
RECREW_TYPES = {79, 100}
ABILITY_TYPES = {14, 72, 132}
UPGRADE_TYPES = {16, 17, 69, 82, 135, 136}
REINFORCE_TYPES = {68, 81, 115}
POSITIONAL_TYPES = {62, 66, 67, 71, 72, 128, 13, 11, 12}
BG_PURCHASE = 138


def mmss(tick):
    total = int(tick) // TICKS_PER_SEC
    return f"{total // 60:02d}:{total % 60:02d}"


class Player:
    __slots__ = ('slot', 'team', 'name', 'faction', 'side')

    def __init__(self, slot, team, name, faction):
        self.slot = slot
        self.team = team
        self.name = name
        self.faction = faction
        self.side = 'AXIS' if faction in AXIS_FACTIONS else 'ALLIES'

    def __repr__(self):
        return f"<slot{self.slot} {self.name} {self.faction} {self.side}>"


class Command:
    __slots__ = ('tick', 'type', 'slot', 'payload')

    def __init__(self, tick, ctype, slot, payload):
        self.tick = tick
        self.type = ctype
        self.slot = slot
        self.payload = payload

    @property
    def name(self):
        return COMMAND_TYPES.get(self.type, f'UNKNOWN_{self.type}')

    def coords(self):
        """Most positional commands carry (x, y_height, z) as the last 12 bytes."""
        p = self.payload
        if len(p) < 12:
            return None
        x, y, z = struct.unpack_from('<fff', p, len(p) - 12)
        if abs(x) < 600 and abs(z) < 600 and -80 < y < 300 and (abs(x) > 0.01 or abs(z) > 0.01):
            return (x, z)
        return None

    def scan_pbgids(self, lookup):
        """Slide a u32 window over the payload and collect ids present in the
        blueprint table. Reliable for ability/upgrade commands whose field
        offsets vary by subtype."""
        hits = []
        p = self.payload
        for i in range(len(p) - 3):
            v = struct.unpack_from('<I', p, i)[0]
            if v > 1000 and v in lookup:
                hits.append(v)
        return hits


class Replay:
    def __init__(self, path):
        self.path = path
        self.data = open(path, 'rb').read()
        self.timestamp = None
        self.map = None
        self.players = {}        # slot -> Player
        self.commands = []
        self.chat = []           # (tick, speaker, message)
        self.events = []         # (tick, kind, detail) for non-tick stream chunks
        self.max_tick = 0
        self._parse()

    # ---------- container ----------

    def _parse(self):
        d = self.data
        if d[4:11] != b'COH3_RE':
            raise ValueError(f"not a CoH3 replay (magic={d[4:12]!r})")
        first = d.find(b'Relic Chunky')
        self.timestamp = d[12:first].decode('utf-16-le', 'replace').strip('\x00').strip()

        off = first
        chunks = []
        for _ in range(2):                      # POST chunky, then INFO/SDSC chunky
            off = self._walk_chunky(off, chunks)
        self.stream_start = off

        info = next((c for c in chunks if c[0] == b'FOLDINFO'), None)
        sdsc = next((c for c in chunks if c[0] == b'DATASDSC'), None)
        if info:
            self._parse_players(info[1], info[1] + info[2])
        if sdsc:
            self._parse_scenario(sdsc[1], sdsc[1] + sdsc[2])
        self._parse_stream(off)

    def _walk_chunky(self, off, out):
        d = self.data
        assert d[off:off + 12] == b'Relic Chunky', f"no chunky at {off}"
        p = off + 12 + 4 + 4 + 4                 # magic, \r\n\x1a\0, version, platform
        return self._walk_chunks(p, out, None)

    def _walk_chunks(self, p, out, end):
        d = self.data
        while end is None or p < end:
            if p + 20 > len(d):
                break
            typ = d[p:p + 4]
            if typ not in (b'FOLD', b'DATA'):
                break
            name = d[p + 4:p + 8]
            size = struct.unpack_from('<I', d, p + 12)[0]
            namelen = struct.unpack_from('<I', d, p + 16)[0]
            hdr = 20 + namelen
            out.append((typ + name, p + hdr, size))
            if typ == b'FOLD':
                self._walk_chunks(p + hdr, out, p + hdr + size)
            p += hdr + size
        return p

    # ---------- header ----------

    def _parse_players(self, start, end):
        """Player records look like:
            01 <u32 namelen> <UTF-16LE name> <u32 team> <u32 slot>
            01 <u32 faclen> <ascii faction>
        The SLOT field is authoritative -- it is the id used in the command
        stream. Header order is NOT slot order, and names can contain
        non-ASCII characters, so never infer slots from name order.
        """
        d = self.data
        p = start
        while p < end - 16:
            if d[p] != 1:
                p += 1
                continue
            namelen = struct.unpack_from('<I', d, p + 1)[0]
            ns = p + 5
            if not (1 <= namelen <= 64) or ns + 2 * namelen + 13 > end:
                p += 1
                continue
            try:
                name = d[ns:ns + 2 * namelen].decode('utf-16-le')
            except UnicodeDecodeError:
                p += 1
                continue
            q = ns + 2 * namelen
            team, slot = struct.unpack_from('<II', d, q)
            if team > 3 or slot > 15 or d[q + 8] != 1:
                p += 1
                continue
            faclen = struct.unpack_from('<I', d, q + 9)[0]
            if not (5 <= faclen <= 32) or q + 13 + faclen > end:
                p += 1
                continue
            faction = d[q + 13:q + 13 + faclen].decode('ascii', 'replace')
            if faction not in FACTIONS:
                p += 1
                continue
            self.players[slot] = Player(slot, team, name, faction)
            p = q + 13 + faclen
        return self.players

    def _parse_scenario(self, start, end):
        d = self.data[start:end]
        for tok in (b'scenarios\\', b'scenarios/'):
            i = d.find(tok)
            if i >= 0:
                j = i
                while j < len(d) and 32 <= d[j] < 127:
                    j += 1
                path = d[i:j].decode('ascii', 'replace')
                self.map = path.rstrip('\\/').split('\\')[-1].split('/')[-1]
                break
        self.points = []
        import re
        pat = re.compile(rb'(victory_point|resource_point_fuel|resource_point_munition|'
                         rb'resource_point_manpower|territory_point)[a-z_,]*')
        for m in pat.finditer(d):
            e = m.end()
            tail = d[e:e + 13]
            if len(tail) == 13 and tail[:5] == b'\xff\xff\xff\xff\x00':
                x, z = struct.unpack_from('<ff', tail, 5)
                if abs(x) < 600 and abs(z) < 600:
                    kind = 'VP' if m.group().startswith(b'victory') else m.group().split(b',')[-1].decode()
                    self.points.append((kind, round(x, 1), round(z, 1)))

    # ---------- command stream ----------

    def _parse_stream(self, off):
        d = self.data
        tick = 0
        while off + 8 <= len(d):
            ctype, size = struct.unpack_from('<II', d, off)
            if off + 8 + size > len(d):
                break
            body = d[off + 8:off + 8 + size]
            if ctype == 0:
                tick = struct.unpack_from('<I', body, 1)[0]
                self.max_tick = max(self.max_tick, tick)
                self._parse_actions(body, tick)
            elif ctype == 1:
                self._parse_side_chunk(body, tick)
            off += 8 + size
        self.stream_end = off

    def _parse_actions(self, body, tick):
        """type-0 tick body: u8 0x20, u32 tick, u32 hash, u32 action_count,
        then action_count records of: u32 index, u32 zero, u32 len, payload."""
        n = struct.unpack_from('<I', body, 9)[0]
        p = 13
        for _ in range(n):
            if p + 12 > len(body):
                break
            length = struct.unpack_from('<I', body, p + 8)[0]
            payload = body[p + 12:p + 12 + length]
            if len(payload) >= 4:
                self.commands.append(Command(tick, payload[2], payload[3], payload))
            p += 12 + length

    def _parse_side_chunk(self, body, tick):
        """type-1 chunks are out-of-band events. subtype 1 = chat."""
        if len(body) < 8:
            return
        subtype = struct.unpack_from('<I', body, 0)[0]
        if subtype == 1 and len(body) > 24:
            try:
                nl = struct.unpack_from('<I', body, 20)[0]
                name = body[24:24 + 2 * nl].decode('utf-16-le')
                q = 24 + 2 * nl
                ml = struct.unpack_from('<I', body, q)[0]
                msg = body[q + 4:q + 4 + 2 * ml].decode('utf-16-le')
                self.chat.append((tick, name, msg))
                return
            except Exception:
                pass
        detail = ''
        if subtype == 0 and len(body) >= 12:
            ent = struct.unpack_from('<I', body, 8)[0]
            if 1000 <= ent < 1016:
                detail = f'player entity {ent} (slot {ent - 1000})'
        self.events.append((tick, f'stream_subtype_{subtype}', detail))

    # ---------- derived ----------

    @property
    def duration(self):
        return mmss(self.max_tick)

    def actions(self):
        """Real player actions: excludes camera + heartbeat + unknown slots."""
        return [c for c in self.commands
                if c.type not in NOISE_TYPES and c.slot in self.players]

    def surrenders(self):
        return [(c.tick, c.slot) for c in self.commands if c.type == 146]

    def outcome(self):
        """Returns (winning_side, losing_side, tick) or (None, None, None).

        A concede is the only outcome the file states directly, and only when
        EVERY member of one side surrendered. A single player quitting a team
        game is not a team concede -- the other three can and do go on to win --
        so that case returns no winner. If nobody surrendered, the match ended
        by annihilation or VP depletion and the file does NOT record who won --
        say so rather than guessing.
        """
        s = self.surrenders()
        if not s:
            return (None, None, None)
        conceded = {slot for _, slot in s if slot in self.players}
        sides = {self.players[slot].side for slot in conceded}
        if len(sides) != 1:
            return (None, None, None)
        loser = sides.pop()
        roster = {slot for slot, p in self.players.items() if p.side == loser}
        if not roster <= conceded:
            return (None, None, None)
        winner = 'ALLIES' if loser == 'AXIS' else 'AXIS'
        return (winner, loser, max(t for t, _ in s))

    def builds(self, lookup=None):
        """[(tick, slot, pbgid, name)] from CMD_BuildSquad.
        pbgid sits at payload offset 35; the owning player entity (1000+slot)
        at 39 -- cross-check them, they should agree with payload[3]."""
        out = []
        for c in self.commands:
            if c.type != 3 or len(c.payload) < 44:
                continue
            pbgid = struct.unpack_from('<I', c.payload, 35)[0]
            ent = struct.unpack_from('<I', c.payload, 39)[0]
            slot = ent - 1000 if 1000 <= ent < 1016 else c.slot
            name = lookup.get(pbgid, {}).get('name') if lookup else None
            out.append((c.tick, slot, pbgid, name or f'pbgid:{pbgid}'))
        return out

    def verify_slots(self, lookup):
        """Cross-check each slot's built units against its header faction.

        This is the single most important sanity check in the whole parser: if
        it fails, every per-player claim you make is attributed to the wrong
        human. Returns a list of problem strings (empty == consistent).
        """
        race_of = {'afrika_korps': 'afrika_korps', 'germans': 'german',
                   'british_africa': 'british_africa', 'americans': 'american'}
        seen = collections.defaultdict(collections.Counter)
        for tick, slot, pbgid, _ in self.builds(lookup):
            race = (lookup.get(pbgid) or {}).get('race')
            if race:
                seen[slot][race] += 1
        problems = []
        for slot, counter in seen.items():
            pl = self.players.get(slot)
            if not pl:
                problems.append(f"builds from unknown slot {slot}")
                continue
            expect = race_of.get(pl.faction)
            top = counter.most_common(1)[0][0]
            # british_africa units are filed under both 'british' and 'british_africa'
            if expect and not (top == expect or top.startswith(expect.split('_')[0])):
                problems.append(
                    f"slot {slot} ({pl.name}) header says {pl.faction} but built {top} units")
        return problems


# ---------- blueprint lookup ----------

DATA_URLS = {
    'sbps': 'https://raw.githubusercontent.com/cohstats/coh3-data/master/data/sbps.json',
    'abilities': 'https://raw.githubusercontent.com/cohstats/coh3-data/master/data/abilities.json',
    'battlegroup': 'https://raw.githubusercontent.com/cohstats/coh3-data/master/data/battlegroup.json',
    'ebps': 'https://raw.githubusercontent.com/cohstats/coh3-data/master/data/ebps.json',
}
DEFAULT_SETS = ('sbps', 'abilities', 'battlegroup')
# The bundled cache sits next to this file, so look there first -- a CWD-relative
# path misses it whenever the script is run from anywhere but scripts/, and the
# fallback is a ~110 MB download.
CACHE_PATHS = (os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            'coh3_pbgid_cache.json'),
               'coh3_pbgid_cache.json',
               os.path.expanduser('~/.cache/coh3-rec/pbgid.json'))


def load_lookup(cache=None, sets=DEFAULT_SETS, quiet=False):
    """pbgid -> {name, race, kind, path}. Builds and caches on first use.

    The source files total ~110 MB, so building takes a minute or two; the
    resulting cache is small and instant to reload.
    """
    candidates = [cache] if cache else list(CACHE_PATHS)
    for path in candidates:
        if path and os.path.exists(path):
            with open(path) as fh:
                lk = {int(k): v for k, v in json.load(fh).items()}
            for rec in lk.values():          # tolerate caches from older versions
                if 'category' not in rec:
                    parts = rec.get('path', '').split('/')
                    rec['category'] = parts[-2] if len(parts) > 1 else ''
            return lk
    return build_lookup(candidates[0] or CACHE_PATHS[0], sets, quiet)


def build_lookup(cache_path, sets=DEFAULT_SETS, quiet=False):
    import urllib.request
    out = {}
    for key in sets:
        url = DATA_URLS[key]
        if not quiet:
            print(f"  fetching {key}...", flush=True)
        with urllib.request.urlopen(url, timeout=300) as resp:
            blob = json.loads(resp.read().decode('utf-8'))
        found = _walk_pbgids(blob, [], key)
        for pbgid, rec in found.items():
            out.setdefault(pbgid, rec)
        if not quiet:
            print(f"    {len(found)} ids", flush=True)
    os.makedirs(os.path.dirname(os.path.abspath(cache_path)) or '.', exist_ok=True)
    with open(cache_path, 'w') as fh:
        json.dump({str(k): v for k, v in out.items()}, fh)
    if not quiet:
        print(f"  cached {len(out)} blueprint ids -> {cache_path}", flush=True)
    return out


def _walk_pbgids(obj, path, kind, out=None):
    if out is None:
        out = {}
    if isinstance(obj, dict):
        pbgid = obj.get('pbgid')
        if isinstance(pbgid, (int, float)) and path:
            race = path[1] if len(path) > 1 and path[0] == 'races' else (path[0] if path else '')
            out.setdefault(int(pbgid), {
                'name': path[-1], 'race': race, 'kind': kind,
                'category': path[-2] if len(path) > 1 else '',
                'path': '/'.join(path)})
        for k, v in obj.items():
            if isinstance(v, dict):
                _walk_pbgids(v, path + [k], kind, out)
    return out


# ---------- geometry ----------

def team_anchors(replay):
    """Estimate each side's base from the earliest positional command per player.

    Naive averaging breaks when one player's first recorded order is already at
    midfield -- that single outlier drags the whole side's anchor forward and
    every depth number after it is wrong. So: seed each side with the member
    sitting furthest from the enemy's positions (that one is certainly at home),
    then average only the teammates clustered near that seed.
    """
    firsts = {}
    for c in replay.commands:
        if c.slot in replay.players and c.slot not in firsts and c.type in POSITIONAL_TYPES:
            xy = c.coords()
            if xy:
                firsts[c.slot] = xy
    by_side = collections.defaultdict(list)
    for slot, xy in firsts.items():
        by_side[replay.players[slot].side].append(xy)

    anchors = {}
    for side, pts in by_side.items():
        other = [p for s2, ps in by_side.items() if s2 != side for p in ps]
        if not pts:
            continue
        if other:
            seed = max(pts, key=lambda p: min(math.dist(p, q) for q in other))
        else:
            seed = pts[0]
        near = [p for p in pts if math.dist(p, seed) <= 110] or [seed]
        anchors[side] = (sum(p[0] for p in near) / len(near),
                         sum(p[1] for p in near) / len(near))
    return anchors, firsts


def anchor_quality(replay, anchors):
    """Sanity-check estimated base anchors.

    Both bases should sit a similar distance from the middle of the playable
    area. A base estimate can only ever be dragged TOWARD the centre (by a
    player whose first recorded order was already forward), never away, so a
    side whose anchor is markedly closer to centre than its opponent's is
    probably poisoned -- and every depth number computed from it is inflated.

    Returns (ratio, centre, warning_or_None). Auto-correcting this was tried
    and rejected: reflecting the good anchor through the centre fixes some maps
    and badly breaks others, because bases are not reliably symmetric. Report
    it and let the analyst override with verified coordinates instead.
    """
    xs, zs = [], []
    for c in replay.commands:
        if c.type in POSITIONAL_TYPES:
            xy = c.coords()
            if xy:
                xs.append(xy[0])
                zs.append(xy[1])
    if not xs or len(anchors) < 2:
        return (None, None, None)
    centre = ((min(xs) + max(xs)) / 2, (min(zs) + max(zs)) / 2)
    d = {k: math.dist(v, centre) for k, v in anchors.items()}
    lo = min(d, key=d.get)
    ratio = d[lo] / max(d.values())
    warn = None
    if ratio < 0.85:
        warn = (f"{lo} anchor sits {ratio:.0%} as far from map centre as the other side's. "
                f"It is probably pulled inward by an early forward order, which INFLATES "
                f"every depth value. Verify against the per-player first-order positions "
                f"below and re-run with --anchors if it looks wrong.")
    return (ratio, centre, warn)


def make_projector(anchors, side='AXIS'):
    """Returns (depth, lateral) functions.

    depth: 0 at `side`'s base, 100 at the opponent's base -- so >50 means the
    player is operating in enemy territory. lateral: signed offset
    perpendicular to the base-to-base axis, in world units. Players with
    similar lateral values are contesting the same lane, which is how you
    detect two teammates stacked in one corridor.
    """
    other = 'ALLIES' if side == 'AXIS' else 'AXIS'
    if side not in anchors or other not in anchors:
        return None, None
    ax, az = anchors[side]
    bx, bz = anchors[other]
    dx, dz = bx - ax, bz - az
    L = math.hypot(dx, dz) or 1.0
    ux, uz = dx / L, dz / L

    def depth(x, z):
        return ((x - ax) * ux + (z - az) * uz) / L * 100

    def lateral(x, z):
        return -(x - ax) * uz + (z - az) * ux

    return depth, lateral
