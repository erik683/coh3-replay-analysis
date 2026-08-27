"""
coh3stats.py -- pull a Company of Heroes 3 match's END-GAME stats (kills, losses,
damage, veterancy, resources) and its replay file from coh3stats.com.

Why this exists: a .rec is an INPUT LOG. It records what every player *did* but
never what those actions *achieved* -- no kills, losses, damage or VP. Those live
in Relic's match-history API, which coh3stats.com scrapes and republishes. This
module fetches them, so the two halves can be reported together:

    API  = WHAT happened   (who killed/lost what, damage, captures, veterancy)
    .rec = HOW they played  (build orders, retreat bursts, territory, lanes)

Keep the halves labelled and separate in the report. An API kill count and a
.rec retreat burst are different kinds of fact; never fuse them into one claim.

Access notes (all verified against the live service):
  * Match/player JSON comes from the coh3stats cache proxy and requires a
    browser-style Referer/Origin or it returns a short "forbidden" body. The
    proxy is also intermittently flaky, so _get() retries.
  * The replay download at replays.coh3stats.com/<id>.rec is a plain CDN GET:
    200 with the .rec if coh3stats has already materialised it, a 404 HTML page
    if not. Materialising a missing replay is a POST behind a Cloudflare
    JS-challenge that a headless client cannot solve -- so when the direct GET
    404s, a human must click "Download Replay" on the match page (their browser
    solves the challenge) and hand the file over. See download_replay().
"""

import json
import re
import sys
import time
import urllib.parse
import urllib.request

# ---- your group's anchor -------------------------------------------------
# The report is centred on the anchor's team. The wider friend group plays as a
# 2-4 stack, sometimes with randoms filling the rest, so membership is learned
# over time rather than hard-coded -- but the anchor pins "our side" in every
# game they are in. Override per-run with --anchor.
ANCHOR_PROFILE_ID = 1101261
ANCHOR_ALIAS = "DeathStyle"

# ---- hosts (from coh3-stats config.ts) -----------------------------------
CACHE_PROXY = "https://cache.coh3stats.com"
REPLAY_STORAGE = "https://replays.coh3stats.com"
RELIC_API = "https://coh3-api.reliclink.com"

_HEADERS = {
    "Referer": "https://coh3stats.com/",
    "Origin": "https://coh3stats.com",
    "User-Agent": "Mozilla/5.0 (coh3-replay-analysis skill)",
}

# race_id -> faction (matches the names the .rec parser uses, so the two
# sources join on faction+alias). From coh3-stats src/coh3/coh3-data.ts.
RACE = {129494: "americans", 137123: "germans", 197345: "british",
        198437: "afrika_korps", 203852: "british_africa"}
AXIS = {"germans", "afrika_korps"}
MATCHTYPE = {0: "Custom", 1: "1v1 ranked", 2: "2v2 ranked", 3: "3v3 ranked",
             4: "4v4 ranked", 20: "1v1", 21: "2v2", 22: "3v3", 23: "4v4"}


# ---- fetch ---------------------------------------------------------------

def _get(url, headers=None, tries=6, timeout=30):
    """GET with retries. The cache proxy occasionally answers a valid request
    with a short 'forbidden' body; treat anything implausibly small as a miss
    and retry."""
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=headers or _HEADERS)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                body = r.read()
            if len(body) > 400 or b'"error"' not in body:
                return body
            last = body            # forbidden/short -> retry
        except Exception as e:      # noqa: BLE001
            last = e
        time.sleep(1.5 * (i + 1))
    raise RuntimeError(f"GET failed after {tries} tries: {url}\n  last: {str(last)[:200]}")


def parse_match_id(arg):
    """Accept a bare id, or any coh3stats /matches/<id> URL."""
    s = str(arg).strip()
    m = re.search(r'matches/(\d+)', s) or re.fullmatch(r'\d+', s)
    if not m:
        raise ValueError(f"could not find a match id in {arg!r}")
    return int(m.group(1) if m.lastindex else m.group(0))


def parse_profile_id(arg):
    s = str(arg).strip()
    m = re.search(r'players/(\d+)', s) or re.fullmatch(r'\d+', s)
    if not m:
        raise ValueError(f"could not find a profile id in {arg!r}")
    return int(m.group(1) if m.lastindex else m.group(0))


def get_match(match_id):
    url = f"{CACHE_PROXY}/sharedAPIGen2Http/matches/{match_id}"
    d = json.loads(_get(url))
    if "match" not in d:
        raise RuntimeError(f"match {match_id}: {d.get('error', d)}")
    return d["match"]


def get_player_card(profile_id):
    return json.loads(_get(f"{CACHE_PROXY}/sharedAPIGen2Http/players/{profile_id}"))


def get_relic_personal_stat(profile_ids, title="coh3"):
    ids = "[" + ",".join(str(i) for i in profile_ids) + "]"
    url = (f"{RELIC_API}/community/leaderboard/getpersonalstat"
           f"?profile_ids={urllib.parse.quote(ids)}&title={title}")
    return json.loads(_get(url, headers={"User-Agent": _HEADERS["User-Agent"]}))


def _cache_dir():
    import os
    d = os.path.expanduser("~/.cache/coh3-rec/replays")
    os.makedirs(d, exist_ok=True)
    return d


def download_replay(match_id, dest_dir=None):
    """Try the direct CDN GET. Returns a path on success, None if the replay is
    not materialised (the caller then asks the user to download it manually).
    Replays land in ~/.cache/coh3-rec/replays by default, not the skill tree."""
    import os
    dest_dir = dest_dir or _cache_dir()
    url = f"{REPLAY_STORAGE}/{match_id}.rec"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _HEADERS["User-Agent"]})
        with urllib.request.urlopen(req, timeout=60) as r:
            body = r.read()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise
    if body[4:11] != b"COH3_RE":          # 404 pages come back as HTML
        return None
    path = os.path.join(dest_dir, f"{match_id}.rec")
    with open(path, "wb") as fh:
        fh.write(body)
    return path


# ---- report --------------------------------------------------------------

def _counters(row):
    c = row.get("counters")
    return json.loads(c) if isinstance(c, str) else (c or {})


def _players(match):
    """Normalise each report row to a flat dict, sorted anchor-team first."""
    out = []
    for r in match["matchhistoryreportresults"]:
        c = _counters(r)
        fac = RACE.get(r.get("race_id"), str(r.get("race_id")))
        out.append({
            "pid": r["profile_id"],
            "alias": (r.get("profile") or {}).get("alias", str(r["profile_id"])),
            "team": r["teamid"],
            "faction": fac,
            "side": "AXIS" if fac in AXIS else "ALLIES",
            "win": r.get("resulttype") == 1,
            "c": c,
        })
    return out


def print_match(match, anchor=ANCHOR_PROFILE_ID, out=None):
    P = _players(match)
    anchor_team = next((p["team"] for p in P if p["pid"] == anchor), None)
    # anchor's team first, then by team, then by damage desc
    P.sort(key=lambda p: (p["team"] != anchor_team, p["team"], -p["c"].get("dmgdone", 0)))

    dur = match["completiontime"] - match["startgametime"]
    mt = MATCHTYPE.get(match["matchtype_id"], f"type {match['matchtype_id']}")
    win_team = next((p["team"] for p in P if p["win"]), None)

    line = "=" * 92
    pr = (lambda s="": out.append(s)) if out is not None else print
    pr(line); pr("MATCH  (coh3stats end-game report -- Relic-recorded outcomes)"); pr(line)
    pr(f"match id    {match['id']}   ({mt}, {match.get('description','')})")
    pr(f"map         {match['mapname']}")
    pr(f"duration    {dur // 60:02d}:{dur % 60:02d}   ({dur}s)")
    pr(f"result      team {win_team} WON")
    if anchor_team is not None:
        pr(f"anchor      {ANCHOR_ALIAS} (#{anchor}) on team {anchor_team} "
           f"-> {'WON' if anchor_team == win_team else 'LOST'}")
    pr("")

    hdr = (f"{'player':16s}{'faction':15s}{'tm':>3}{'W':>2}  {'kills':>6} "
           f"{'sqk':>4}{'vk':>4} | {'losses':>7}{'sql':>4}{'vl':>4}{'vab':>4} | "
           f"{'dmg':>7}{'cap':>4} {'vet s/v':>8}")
    pr(hdr)
    star = lambda p: "*" if p["pid"] == anchor else " "  # noqa: E731
    for p in P:
        c = p["c"]
        pr(f"{star(p)}{p['alias'][:15]:15s}{p['faction']:15s}{p['team']:>3}"
           f"{'Y' if p['win'] else '.':>2}  "
           f"{c.get('ekills',0):>6} {c.get('sqkill',0):>4}{c.get('vkill',0):>4} | "
           f"{c.get('edeaths',0):>7}{c.get('sqlost',0):>4}{c.get('vlost',0):>4}"
           f"{c.get('vabnd',0):>4} | {c.get('dmgdone',0):>7}{c.get('pcap',0):>4} "
           f"{str(c.get('svetrank',0))+'/'+str(c.get('vvetrank',0)):>8}")

    pr("")
    for team in sorted({p["team"] for p in P}):
        ts = [p for p in P if p["team"] == team]
        tot = lambda k: sum(p["c"].get(k, 0) for p in ts)  # noqa: E731
        tag = "(anchor) " if team == anchor_team else ""
        pr(f"team {team} {tag}{'WON ' if team == win_team else 'LOST'}  "
           f"kills={tot('ekills'):5d} sqk={tot('sqkill'):3d} vk={tot('vkill'):3d}  "
           f"losses={tot('edeaths'):5d} sqlost={tot('sqlost'):3d} vlost={tot('vlost'):3d}  "
           f"dmg={tot('dmgdone'):7d}")
    pr("")
    pr("kills: ekills=models killed, sqk=squads wiped, vk=vehicles killed. "
       "losses: edeaths=models lost,")
    pr("sql=squads lost, vl=vehicles lost, vab=vehicles abandoned. dmg=damage "
       "dealt, cap=points captured,")
    pr("vet=final squad/vehicle veterancy rank. These are Relic's simulated "
       "outcomes -- NOT in the .rec.")
    return P


def print_player_trends(card, personal=None, out=None):
    pr = (lambda s="": out.append(s)) if out is not None else print
    sg = (personal or {}).get("statGroups", [{}])
    mem = (sg[0].get("members") or [{}])[0] if sg else {}
    stats = (personal or {}).get("leaderboardStats", [])
    # per-mode, per-race leaderboard ids (coh3-data.ts leaderboardsIDAsObject)
    LB = {}
    for mode, races in {
        "1v1": {2130255: "US", 2130257: "UK", 2130259: "DAK", 2130261: "Wehr"},
        "2v2": {2130300: "US", 2130302: "UK", 2130304: "DAK", 2130306: "Wehr"},
        "3v3": {2130329: "US", 2130331: "UK", 2130333: "DAK", 2130335: "Wehr"},
        "4v4": {2130353: "US", 2130356: "UK", 2130358: "DAK", 2130360: "Wehr"},
    }.items():
        for lid, race in races.items():
            LB[lid] = f"{mode} {race}"
    line = "=" * 78
    pr(line); pr(f"PLAYER  {mem.get('alias','?')}  (#{mem.get('profile_id','?')}, "
                 f"{mem.get('country','')})"); pr(line)
    pr(f"{'leaderboard':14s}{'W':>5}{'L':>5}{'win%':>6}{'streak':>7}"
       f"{'rating':>7}{'rank':>7}")
    for s in sorted(stats, key=lambda s: -(s.get("wins", 0) + s.get("losses", 0))):
        w, l = s.get("wins", 0), s.get("losses", 0)
        if w + l == 0:
            continue
        name = LB.get(s.get("leaderboard_id"), str(s.get("leaderboard_id")))
        pr(f"{name:14s}{w:>5}{l:>5}{100*w/(w+l):>5.0f}%{s.get('streak',0):>7}"
           f"{s.get('rating',0):>7}{s.get('rank',0):>7}")


# ---- CLI -----------------------------------------------------------------

def _cli():
    import argparse
    import os
    import subprocess
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    pm = sub.add_parser("match", help="end-game stats + replay for a match")
    pm.add_argument("match", help="match id or coh3stats /matches/<id> URL")
    pm.add_argument("--rec", help="use this local .rec instead of downloading")
    pm.add_argument("--anchor", type=int, default=ANCHOR_PROFILE_ID)
    pm.add_argument("--no-replay", action="store_true",
                    help="API stats only; skip the replay analysis")
    pm.add_argument("--json", help="write the raw match JSON here")

    pp = sub.add_parser("player", help="long-term trends for a profile")
    pp.add_argument("player", nargs="?", default=str(ANCHOR_PROFILE_ID),
                    help="profile id or /players/<id> URL (default: anchor)")

    args = ap.parse_args()
    here = os.path.dirname(os.path.abspath(__file__))

    if args.cmd == "player":
        pid = parse_profile_id(args.player)
        card = None
        try:
            card = get_player_card(pid)
        except Exception as e:      # noqa: BLE001
            print(f"(player card unavailable: {e})", file=sys.stderr)
        personal = get_relic_personal_stat([pid])
        print_player_trends(card, personal)
        return

    mid = parse_match_id(args.match)
    match = get_match(mid)
    if args.json:
        with open(args.json, "w") as fh:
            json.dump(match, fh, indent=2)
    print_match(match, anchor=args.anchor)

    if args.no_replay:
        return

    rec = args.rec
    if not rec:
        print(f"\nlooking for replay at {REPLAY_STORAGE}/{mid}.rec ...")
        rec = download_replay(mid)
    if rec and os.path.exists(rec):
        print(f"replay: {rec}\n")
        sys.stdout.flush()   # flush our buffered output before the child writes to the fd
        subprocess.run([sys.executable, os.path.join(here, "analyze_rec.py"), rec])
    else:
        print("\n" + "-" * 78)
        print("REPLAY NOT AVAILABLE HEADLESSLY")
        print("-" * 78)
        print("coh3stats has not materialised this .rec yet, and the generate step is\n"
              "behind a browser challenge. To add the input-signature layer (build\n"
              "orders, retreats, territory), open the match page and click\n"
              f"'Download Replay':\n    https://coh3stats.com/matches/{mid}\n"
              "then re-run:\n"
              f"    python3 scripts/coh3stats.py match {mid} --rec <downloaded.rec>\n"
              "The end-game stats above stand on their own without it.")


if __name__ == "__main__":
    _cli()
