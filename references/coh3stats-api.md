# coh3stats / Relic API — end-game stats & replay download

How `scripts/coh3stats.py` gets the data the `.rec` can't carry. All of this was
reverse-engineered from the `cohstats/coh3-stats` frontend and verified against
the live service (Aug 2026). Hosts come from that repo's `config.ts`.

## Hosts

| purpose | host |
|---|---|
| match & player JSON (cache proxy) | `https://cache.coh3stats.com` |
| replay files (R2 CDN) | `https://replays.coh3stats.com` |
| Relic community API (direct) | `https://coh3-api.reliclink.com` |

## Match details (the important one)

```
GET https://cache.coh3stats.com/sharedAPIGen2Http/matches/<matchID>
```

**Must send browser-style headers** or you get
`{"error":"It's forbidden to use COH3 API without approval…"}`:

```
Referer: https://coh3stats.com/
Origin:  https://coh3stats.com
```

The proxy is also intermittently flaky and will occasionally return that short
error to a valid request — retry (the client does, up to 6×).

Response shape (`match` object): `id`, `mapname`, `matchtype_id`,
`description` (e.g. `AUTOMATCH`), `startgametime`, `completiontime` (unix;
duration = the difference), `profile_ids`, `matchurls` (per-player replay keys,
see below), and `matchhistoryreportresults` — one row per player:

- `profile_id`, `teamid`, `resulttype` (**1 = win, 0 = loss**), `race_id`
- `profile.alias` — the in-game name (joins to the `.rec` roster)
- `counters` — a JSON **string** (parse it again) of end-game stats.

### `counters` fields used

| field | meaning |
|---|---|
| `ekills` | enemy models/entities killed |
| `sqkill` | enemy squads wiped |
| `vkill` | enemy vehicles killed |
| `edeaths` | own models lost |
| `sqlost` | own squads lost |
| `vlost` | own vehicles lost |
| `vabnd` | own vehicles abandoned |
| `dmgdone` | damage dealt |
| `pcap` | points captured |
| `svetrank` / `vvetrank` | final squad / vehicle veterancy rank |

Also present (not all displayed): `structdmg`, `objdmh`, `precap`, `vcap`,
`cflags`, `reqearn`/`reqspnt` (manpower), `powearn`/`powspnt`, `gammaspnt`,
`popmax`, `vp0`/`vp1`, `bprod`/`sqprod`/`vprod`/`unitprod`, `wpnpu`, `totalcmds`,
`cpearn`. `elitekill` exists but returns nonsense (negative values observed) —
don't report it.

`race_id`: `129494` american, `137123` german, `197345` british, `198437` dak,
`203852` british_africa (localised "British" but a separate faction).

`matchtype_id`: `0` Custom; `1–4` ranked 1v1…4v4; `20–23` unranked 1v1…4v4;
higher ids are vs-AI. Custom (0) games are generally **not** on coh3stats.

## Replay download

```
GET https://replays.coh3stats.com/<matchID>.rec
```

- **200** + `COH3_RE` magic → the replay is materialised; save and parse it.
- **404** (an HTML body) → not materialised yet.

Materialising a missing replay is a `POST .../matches/<id>/replay` with the
`matchurls` keys as `replayURLs=[{profile_id, replay_id:<key>}, …]`. That
endpoint sits behind a **Cloudflare managed JS challenge**, so a headless script
cannot trigger it — only a real browser can. Practical rule: if the direct GET
404s, have the user click **Download Replay** on the match page (their browser
solves the challenge and materialises it for next time), then pass the file with
`--rec`. The R2 CDN itself is not challenge-walled; only the POST is.

## Player / long-term trends

```
GET https://cache.coh3stats.com/sharedAPIGen2Http/players/<profileID>          # card
GET https://coh3-api.reliclink.com/community/leaderboard/getpersonalstat?profile_ids=[<id>]&title=coh3
```

`getpersonalstat` needs no special headers. It returns `statGroups[0].members[0]`
(alias, `name` = `/steam/<steam64>`, country, level) and `leaderboardStats` —
per **mode × race** wins/losses/streak/rating/rank. The leaderboard ids
(`leaderboardsIDAsObject` in `coh3-data.ts`): 1v1 `2130255/257/259/261`, 2v2
`2130300/302/304/306`, 3v3 `2130329/331/333/335`, 4v4 `2130353/356/358/360`
(order: american, british, dak, german).

## cohdb (alternative replay source)

`https://cohdb.com/api/v1/replays?profile_id=<id>` returns replays a user
uploaded to cohdb, each with a `match_id` (joins to a coh3stats match) and a
`download_link`. No Cloudflare wall, but coverage is limited to what people
chose to upload — a supplementary source, not the primary one.
