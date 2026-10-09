# PPGPool27: project notes

Read this first if you're picking up work on PPGPool27 in a new chat or session. It is the technical map: where things live, how the data flows, how to ship a change and what bites.

The owner keeps the private details (links to the private app copy and its data, design standards, copy voice and house rules) in his `ppgpool27` Claude skill. If you are Claude and that skill isn't loaded, ask him for it before making design or copy decisions.

PPGPool27 is a companion app for a 16-team NHL points pool (12 skaters per team; points are goals plus assists). It shows the standings, projected finish and title odds, last night's damage, tonight's rooting guide, the Pool Pulse stories and a record book. It updates every morning and during games.

## Where everything lives

| What | Where | Notes |
|---|---|---|
| The app (source of truth) | A private Claude artifact owned by Davon, file `index.html` (the link is in his skill) | One HTML page, vanilla JS, no build step. The artifact host wraps it in its own `<html>`/`<head>` skeleton |
| Data and pipeline scripts | Same artifact | `results.json` (what the app reads), the private inputs file, the four pipeline scripts (`prep`, `model`, `check`, `pulse`, stored as .txt), `live.json`, headshots in `img/p/`, NHL logos in `img/t/`, `icons/`, `manifest.webmanifest`, `og.png` |
| The public website | This repo, served by GitHub Pages at https://davondaneils.github.io/ppgpool27/ | A built copy of the app plus `results.json`. This is the link members use |
| Pool team crests | A separate Claude design artifact, "Pool Team Logos" | In the app they're inline SVGs in the `LOGO` map, with team colours in `BRANDC` and hues in `BRANDH` |
| Morning refresh | Claude scheduled task "Pool Odds daily refresh", 4:52 AM Toronto, daily | Takes about 8 to 10 minutes, so new data lands around 5 AM. Its prompt holds the full step list |
| Live scores (artifact) | Claude scheduled task "Pool Odds live scores", at :05 past 4, 6, 8, 9, 10 and 11 PM and midnight, Toronto | Writes `live.json` to the artifact only |
| Live scores (website) | `.github/workflows/site.yml` + `scripts/live.py` | Asks for every 10 minutes on game nights; fetches NHL.com scores into `live.json` and redeploys only when something changed. See Open items: GitHub rarely runs it on time |
| Live watcher (website) | `.github/workflows/live.yml` + `scripts/live_watch.py` | Stays up through a game night, checks NHL.com every 2 minutes and starts the Site workflow after every change (and every 8 minutes for the clock while games are live). Starts every 15 to 30 minutes from 6:40 to 10:10 PM Toronto, plus hourly 12:40 to 5:40 PM on weekends (approved Oct 9; treat these times like a scheduled-task schedule); `kick` just redeploys once |

Personal links: `https://davondaneils.github.io/ppgpool27/?team=<slug>` preselects a team on someone's first visit. The slug is the team name lowercased, `&` turned into `and`, and every other run of non-alphanumeric characters turned into `-` (for example `lord-of-the-rinks`, `debits-and-checks`, `matthew-s-team`). `?tour` replays the onboarding.

## How a day works

1. **4:52 AM Toronto, the morning refresh** (Claude scheduled task). It reads the artifact's files, then:
   - pulls each NHL team's skater stats from Hockey-Reference, line combinations and power-play units from DailyFaceoff, the schedule, last night's official NHL.com scoresheets and the injury report (all through WebFetch, because the shell can't reach those sites);
   - runs `prep.py` (merge raw data), `model.py` (projections and a 40,000-run season simulation), `check.py` (cross-check last night against NHL.com, keep game logs, bridge missing games) and `pulse.py` (find the day's storylines);
   - writes the day's Pool Pulse cards from those facts (and, on Mondays, the weekly recap);
   - republishes the artifact, then pushes `results.json` to this repo as "Morning data YYYY-MM-DD", which redeploys the site;
   - messages the owner on Mondays, and on other days only when something needs his attention.
2. **Game nights.** The GitHub workflow refreshes the site's `live.json`; the Claude live task refreshes the artifact's.
3. **In the app.** `results.json` and `live.json` are fetched when the page loads, and an open app keeps itself current (`freshen()`): it checks again whenever it comes back into view, `results.json` every 10 minutes and, on game nights (or while games are live), `live.json` every 2 minutes. Changes are applied in place (`quietRender()`): no reload, scroll positions kept, entrance animations not replayed, an open game sheet updated where it is, and when a new morning's data arrives the overnight summary shows as if the app had just been opened. Live points are layered on top (`applyLive`) only when `live.json` is dated today (or yesterday before 6 AM) and is newer than `results.asof`, so last night's games are never counted twice. Live points flow into everything that shows them: the Tonight header, team totals and standings, player totals and the standings chart.

`asof` is the date of the last games included (yesterday), not the date the refresh ran. The Pool Pulse header shows the morning after `asof`.

**The bridge.** Hockey-Reference often posts games hours late. For teams it hasn't caught up on, `check.py` credits last night's goals and assists from the NHL.com scoresheets so standings, streaks and the Pulse aren't a day behind (`results.bridge` lists which teams). The next morning the stats source has caught up and its season totals replace these provisional numbers.

## Data files

**`results.json`** (public; the only data file in this repo). Main keys:
- `asof`, `season_games`, `team_gp`
- `teams[]`: `name`, `banked` (points so far), `ros` (projected rest of season), `sim` (projected final), `p10`/`p90`, `win` and `top3` (odds), `rank_proj`, `rank_now`, `rank_ros`, `players[]` (season stats, rate, availability, line and power-play unit, notes and injury details, `susp`, `log`, `last`)
  - `susp` (optional): `{games, from_gp, reason, source}`, set by hand in the private inputs file when a pool player is suspended. `from_gp` is his NHL team's games played when the suspension started; the app counts games left from `team_gp`, shows a Suspended tag and the reason, and `model.py` leaves those games out of his projection. Remove it once he's back
- `daily[]`: one snapshot per morning (rank, banked points and odds per team). It powers the Race tab's "Move" column (places moved since the previous update, or since puck drop during games), the hero's weekly comparisons and the standings chart
- `pulse`: `{asof, items[]}`, today's Pool Pulse cards. Item fields: `type`, `polarity` (`up`, `down` or `neutral`), `team`, `player`, `kicker`, `stat`, `headline`, `body`, and optionally `label` (the small word above the stat; the app falls back to a per-type default, then "Pool") and `breaking`
- `records`, `schedule`, `check`, `bridge`, `recap`, `lens`, `recap_archive`, `history`

**The private inputs file** lives only on the artifact and never goes in this repo: rosters with rates and availability, weekly bookkeeping, the writer notes the morning task follows, and other background notes.

**`live.json`**: `{"date":"YYYY-MM-DD","updated":"<ISO time>","games":[{"away","home","ag","hg","state","period","clock","goals":[{"team","scorer","assists":[...]}]}]}`. `state` is NHL.com's gameState: FUT, PRE, LIVE, CRIT, FINAL or OFF.

## App anatomy

- **Tabs** (`TABS` / `RENDER`): Today, Race, My team, League, Recap. Bottom tab bar on phones, top bar on desktop.
- **Today, top to bottom (the order is fixed on purpose):** ticker, hero, Tonight (rooting guide), Pool Pulse, Watch list, Hot and cold, Record book, footer row.
- **Useful functions:** `today()`, `race()`, `mine()`, `league()`, `recap()`, `heroLine()`, `pulseHTML()`, `tickerHTML()`, `hotCold()`, `recordBook()`, `gameSheet()`, `howSheet()`, `drawStand()`, `applyLive()`, `liveOn()`, `liveNew()`, `freshen()`, `quietRender()`, `pickTeam()`, `onboard()`, `setTeam()`, `SH(kicker, title, meta)` (section heading).
- **Re-rendering after a data change:** use `quietRender()`, not `rerender()`. It adds a `quiet` class that switches off entrance animations (`.rise`, banner sway, Hot and cold reveals, chart draws), so updates don't make the page jump. A normal tab switch (`setTab`) removes it, so tabs still animate in. New entrance effects need a matching `.quiet` rule.
- **Saved settings** (localStorage):
  - JSON-encoded through the `store` helper: `pool.me` (your team), `pool.stars` (rivals), `pool.tab`, `pool.onboarded`, `pool.ovn.<team>` and `pool.seen.<team>` (overnight summary and move celebrations already shown), and view choices (`pool.raceView`, `pool.leagueView`, `pool.rosterSort`, `pool.recapWeek`, `pool.lens`, `pool.h2h`, `pool.obAll`, `pool.seenRows`, `pool.wiPlayer`).
  - Plain strings: `pool.theme` (`light` or `dark`; unset means follow the device) and `pool.splash` (the UTC date the intro last played).
- **Starred rivals** are "threats" on game nights and get their own watch list. Onboarding suggests up to three; the Rosters star has no cap.

## Shipping a change

1. **Read before you write.** Get the current page with the Artifact tool: `read` on the artifact's URL without a `path` (a read with `path` doesn't count as having seen the latest version, and the publish gets refused). The read comes back wrapped in the host's skeleton; both tools below accept that as is. The scheduled tasks republish the artifact daily and on game nights, so never work from an old copy.
2. **Edit**, then syntax-check the scripts: pull out the `<script>` blocks and run `node --check` on them.
3. **Preview**, from the repo root:
   `python3 tools/preview.py edited.html --compare original.html`
   It screenshots every tab at 390 and 1280 px (light and dark) into `preview-shots/` and flags anything poking past the screen edge, console errors and missing files. With `--compare`, flags the page already had are marked "(already there)", so you only chase what your change introduced. Add `--widths 375,390,1280` for layout work, `--themes light,dark,toggle` when you touch dark-mode CSS, `--live some-live.json` for game-night views and `--fresh` for the first-visit flow. Then look at the shots, phone first.
4. **Publish to the artifact**: Artifact `publish` with `url` set to the artifact link and `file_path` set to your edited page. Pass other files only if you changed them (files left out are kept). If the publish reports a conflict, merge your change into the newer version it hands back and publish again.
5. **Publish to the website**: `git pull --rebase` first (it refuses to run with uncommitted changes), then `python3 tools/build_site.py edited.html`, stage only `index.html` and `version.json`, commit as `davondaneils` with a short plain message, and push. The push redeploys the site, and the new `version.json` makes copies people already have open reload themselves.
6. **Confirm the deploy**: `gh api "repos/davondaneils/ppgpool27/actions/runs?per_page=4"` shows the run for your commit and whether it succeeded (run logs and the Pages settings aren't reachable from Claude). github.io itself isn't reachable from the sandbox. A new deploy can take a minute or two to show on phones.
7. **Data-only fixes**: publish the changed `results.json` (and the private inputs file, if changed) to the artifact, copy `results.json` into this repo, commit and push.
8. **Pipeline script changes**: edit the script, publish it to the artifact as `data/<name>.txt`. The next morning run picks it up.

Getting push access in a new Claude session: add the repo with the `add_repo` tool (owner `davondaneils`, repo `ppgpool27`, access `push`), then clone it. Reading this file only needs `curl -s https://raw.githubusercontent.com/davondaneils/ppgpool27/main/PROJECT.md`.

## Gotchas

- **Network.** The cloud shell can't reach Hockey-Reference, DailyFaceoff, the NHL API or github.io; use WebFetch for those. GitHub itself (git, `gh api`, raw.githubusercontent.com) works.
- **No sideways scrolling, ever.** Full-width bands size to `--vw` (the page's client width), not `100vw`, and the page clips horizontal overflow. So anything too wide gets silently cut off instead of scrolling. That's why `tools/preview.py` checks for it.
- **CSS class collisions.** It's one big stylesheet and short class names collide (`.bar`, `.big`, `.h2`, `.gt` and `.kv` all bit). Prefix new classes per component (`.pz-*` Pulse, `.hx-*` hero, `.tng-*` Tonight, `.gr` game tiles, `.gs-*` game sheet) and grep before adding one: some prefixes are shared (`.ob-*` is used by onboarding, the hero's odds arrows and old odds-board code).
- **Dark mode is defined twice**: under `@media (prefers-color-scheme:dark){:root:not([data-theme="light"]) ...}` (device setting) and under `:root[data-theme="dark"] ...` (the in-app toggle). Every new dark rule goes in both.
- **Team colour.** `--me` keeps only the team's hue (`BRANDH`) at a fixed saturation and lightness, so it's a legible version of the team colour, not the exact hex.
- **Escape everything** that goes into HTML with `esc()`, including numbers like "<1%".
- **Shadowed names.** `drawStand()` has a local `L` (a margin) that hides the global live data `L`; use `liveNew()` / `liveDate()` there.
- **Fonts in sandboxes.** Google Fonts is usually blocked, so local screenshots need the real fonts from npm: `tools/preview.py` fetches Barlow Condensed and Inter into `tools/.fonts`. Measure fit with them loaded; fallback fonts have different widths.
- **This repo is public.** Never commit the private inputs file, the pipeline scripts, the artifact's links or anything from the private notes. `.gitignore` blocks the obvious file names as a safety net.

## Open items (as of Oct 9, 2026)

- **Website live scores mostly aren't arriving.** The live watcher (above, on from Oct 9) works around the first cause; Oct 9 is its first night. Two causes:
  - GitHub has run the 10-minute schedule only once since it was added (Oct 9, 3:59 AM Toronto).
  - Pages Source was switched to "GitHub Actions" on Oct 9, so pushes no longer trigger a second branch deploy that drops `live.json`.
- **Live-score wording.** How the odds work and the game sheet both say live scores update "about once an hour". That's true of the artifact, but the website's cadence depends on GitHub (see above).
- **Hero meta line.** It reads "49 back of 1st" without "points", and during games it wraps on phone with a stray leading "·".
- **Pulse stat labels.** Streak, slump and record cards have no default label, so "Pool" shows above their stat.
- **Copy that breaks the house style.** The Recap tab still shows recap text that mentions "the model" (new recaps avoid it from Mon Oct 12, but the archived week keeps it), and its team lines say "Strength from here: Nth of 16", which is jargon.
- **The intro splash is once per UTC day,** so in Toronto it resets at 8 PM instead of greeting the first open of the morning.
- **Morning push.** The Oct 9 refresh was started by hand after the schedule moved to 4:52, and its push to GitHub didn't land (it was pushed manually). Oct 10 is the first real scheduled test; a check is set for 5:20 AM.
- **Similar team colours.** Because `--me` uses only the hue, several teams look alike: Lord of the Rinks and 97 Problems; This Is the Year, Tage Against the Machine and Chugalugs91; Just Here for the Poker, Poppy's Picks and Anthony Scavuzzo; Dom Scavuzzo and Debits & Checks; PhilCap and Peter Will Probably Pick Old Guys. The "bad news" colour (`--bad` #c2410c) is also close to Lord of the Rinks' own colour.
- **Stray file on the artifact.** An old root-level copy of the private inputs file from Oct 8 is still published next to the live one in `data/`.

## Repo layout

```
index.html              built app (from tools/build_site.py; don't hand-edit)
version.json            build stamp that makes open copies reload
results.json            morning data (pushed by the daily refresh)
manifest.webmanifest, icons/, og.png, img/   app icons, link preview, headshots, NHL logos
scripts/live.py         game-night scores for the website
.github/workflows/site.yml   deploy on push + every 10 minutes on game nights
tools/build_site.py     artifact page -> site index.html + version.json
tools/preview.py        local screenshots and layout checks
PROJECT.md              this file
```
