"""Fetch tonight's NHL scores and goals into live.json (same shape the app expects)."""
import json, os, sys, urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

now = datetime.now(ZoneInfo("America/Toronto"))
day = (now - timedelta(days=1) if now.hour < 6 else now).strftime("%Y-%m-%d")

def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "ppgpool27"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)

def name(p):
    if not p:
        return ""
    if isinstance(p, dict):
        f = (p.get("firstName") or {}).get("default", "")
        l = (p.get("lastName") or {}).get("default", "")
        if f or l:
            return (f[:1] + ". " if f else "") + l
        return (p.get("name") or {}).get("default", "")
    return str(p)

try:
    d = get(f"https://api-web.nhle.com/v1/score/{day}")
except Exception as e:
    print("fetch failed:", e)
    sys.exit(0)

games = []
for g in d.get("games", []):
    away, home = g.get("awayTeam", {}), g.get("homeTeam", {})
    st = g.get("gameState", "FUT")
    pd = g.get("periodDescriptor", {}) or {}
    clk = g.get("clock", {}) or {}
    goals = []
    for go in g.get("goals", []) or []:
        sc = go.get("name", {}).get("default") if isinstance(go.get("name"), dict) else None
        if not sc:
            fn = (go.get("firstName") or {}).get("default", "")
            ln = (go.get("lastName") or {}).get("default", "")
            sc = (fn[:1] + ". " if fn else "") + ln
        goals.append({
            "team": go.get("teamAbbrev", {}).get("default") if isinstance(go.get("teamAbbrev"), dict) else go.get("teamAbbrev"),
            "scorer": sc,
            "assists": [name(a) for a in go.get("assists", []) or []],
        })
    games.append({
        "away": away.get("abbrev"), "home": home.get("abbrev"),
        "ag": away.get("score", 0) or 0, "hg": home.get("score", 0) or 0,
        "state": st, "period": pd.get("number", 0) or 0,
        "clock": clk.get("timeRemaining", "") if st in ("LIVE", "CRIT") else "",
        "goals": goals,
    })

active = [g for g in games if g["state"] not in ("FUT", "PRE")]
out = {"date": day, "updated": now.isoformat(timespec="seconds"), "games": games}
changed = False
if active:
    json.dump(out, open("live.json", "w"), separators=(",", ":"))
    # Only redeploy when something actually changed since the last deploy.
    try:
        prev = get("https://davondaneils.github.io/ppgpool27/live.json")
        changed = prev.get("date") != day or prev.get("games") != games
    except Exception:
        changed = True
print(f"{day}: {len(games)} games, {len(active)} started, changed={changed}")
with open(os.environ.get("GITHUB_OUTPUT", "/dev/null"), "a") as f:
    f.write(f"active={'true' if changed else 'false'}\n")
