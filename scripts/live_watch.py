"""Game-night watcher: keeps the website's live scores moving.

GitHub's 10-minute schedule fires rarely, so instead of relying on it this script is started a few
times each evening and stays up for the night. Every 2 minutes it checks NHL.com's scores and, when
a goal, score, period or game state changes (or every 8 minutes while games are live, for the clock),
it starts the Site workflow, which rebuilds live.json and redeploys the site.

It exits early when tonight's first puck drop is more than 75 minutes away (a later start picks it
up), and finishes once every started game is final.
"""
import json, os, subprocess, sys, time, urllib.request
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Toronto")
POLL = 120          # seconds between checks
CLOCK_EVERY = 480   # redeploy at least this often while a game is live
EARLY = 75 * 60     # don't wait longer than this for the first puck drop
LIMIT = 5.6 * 3600  # stay under GitHub's 6-hour job limit
START = time.time()


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "ppgpool27"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def slate():
    now = datetime.now(TZ)
    day = (now - timedelta(days=1) if now.hour < 6 else now).strftime("%Y-%m-%d")
    return day, get(f"https://api-web.nhle.com/v1/score/{day}").get("games", [])


def sig(games):
    out = []
    for g in games:
        out.append([
            g.get("id"), g.get("gameState"),
            (g.get("awayTeam") or {}).get("score"), (g.get("homeTeam") or {}).get("score"),
            (g.get("periodDescriptor") or {}).get("number"),
            [(x.get("playerId"), [a.get("playerId") for a in x.get("assists") or []]) for x in g.get("goals") or []],
        ])
    return json.dumps(out)


def deploy(why):
    print(datetime.now(TZ).strftime("%H:%M"), "deploy:", why, flush=True)
    r = subprocess.run(["gh", "workflow", "run", "site.yml", "--ref", "main"], capture_output=True, text=True)
    if r.returncode:
        print("dispatch failed:", r.stderr.strip(), flush=True)


if os.environ.get("KICK") == "true":
    deploy("manual kick")
    sys.exit(0)

last_sig, last_deploy = None, 0.0
while time.time() - START < LIMIT:
    try:
        day, games = slate()
    except Exception as e:
        print("fetch failed:", e, flush=True)
        time.sleep(POLL)
        continue
    if not games:
        print(day, "no games")
        break
    states = [g.get("gameState", "FUT") for g in games]
    started = [s for s in states if s not in ("FUT", "PRE")]
    live = [s for s in states if s in ("LIVE", "CRIT")]
    if not started:
        first = min(datetime.fromisoformat(g["startTimeUTC"].replace("Z", "+00:00")) for g in games if g.get("startTimeUTC"))
        wait = (first - datetime.now(timezone.utc)).total_seconds()
        if wait > EARLY:
            print(day, f"first puck in {int(wait // 60)} min, leaving it to a later start")
            break
        time.sleep(POLL)
        continue
    s = sig(games)
    if s != last_sig:
        deploy(f"{len(live)} live, {len(started)}/{len(games)} started")
        last_sig, last_deploy = s, time.time()
    elif live and time.time() - last_deploy >= CLOCK_EVERY:
        deploy("clock")
        last_deploy = time.time()
    if len(started) == len(games) and not live and all(st in ("FINAL", "OFF") for st in states):
        print(day, "all games final")
        break
    time.sleep(POLL)
