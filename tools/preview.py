"""Screenshot the app the way members see it, and check the layout, before publishing anything.

Usage (from the repo root):
    python3 tools/preview.py APP_INDEX_HTML [options]

    APP_INDEX_HTML    the app page: the artifact's index.html as an Artifact read returns it, or your
                      edited copy (bare or wrapped both work)
    --compare FILE    the unedited page: flags it already had are marked "(already there)", so you can
                      tell what your change introduced
    --data DIR        folder with results.json, img/ and icons/ (default: the repo root)
    --live FILE       a live.json to test game-night views; its date is set to today so the app
                      treats the games as tonight's (default: none, so no live games)
    --team NAME       whose view to show (default: "Lord of the Rinks")
    --tabs LIST       default: today,race,mine,league,recap
    --widths LIST     default: 390,1280 (phone first). Add 375 for layout changes.
    --themes LIST     light, dark (device set to dark) and toggle (device light, dark picked with the
                      in-app button). Default: light,dark. Use all three when you change dark-mode CSS,
                      because dark rules live in two places.
    --out DIR         where the PNGs go (default: ./preview-shots, which git ignores)
    --fresh           first-visit view: the splash, team picker and onboarding are not skipped

For every shot it prints whether anything pokes past the right edge of the screen (the app must never
scroll sideways), console errors and missing files. Exit code 1 means something new was flagged.
Look at the PNGs too, phone first. Fixed elements (the phone tab bar) appear once, mid-page, in
full-page shots; that's normal.

Fonts: Google Fonts is usually blocked in sandboxes, so Barlow Condensed (the display face) is fetched
once from npm (@fontsource/barlow-condensed) into tools/.fonts. Without it, headings fall back to a
different width and line breaks won't match what members see.
"""
import argparse
import datetime as dt
import functools
import http.server
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import threading
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_site import bare_page, site_document  # noqa: E402  (same wrapper the website uses)

ROOT = Path(__file__).resolve().parent.parent
FONTS = ROOT / "tools" / ".fonts"
WEIGHTS = [(w, s) for w in (600, 700, 800) for s in ("normal", "italic")]
TZ = "America/Toronto"

# Anything wider than the screen that isn't inside a scrolling or clipping container (rails are fine).
OVERFLOW_JS = r"""() => {
  const W = document.documentElement.clientWidth, bad = [];
  const clipped = el => { for (let p = el.parentElement; p && p !== document.body; p = p.parentElement) {
      if (getComputedStyle(p).overflowX !== 'visible') return true; } return false; };
  for (const el of document.querySelectorAll('body *')) {
    const r = el.getBoundingClientRect();
    if (r.width && r.right > W + 1 && !clipped(el) && getComputedStyle(el).position !== 'fixed')
      bad.push((el.id ? '#' + el.id : el.tagName.toLowerCase()) +
        (typeof el.className === 'string' && el.className.trim() ? '.' + el.className.trim().split(/\s+/).join('.') : '') +
        ' +' + Math.round(r.right - W) + 'px');
  }
  return {scrollW: document.documentElement.scrollWidth, clientW: W, poking: bad};
}"""


def ensure_fonts():
    want = [FONTS / f"barlow-condensed-latin-{w}-{s}.woff2" for w, s in WEIGHTS]
    if all(p.exists() for p in want):
        return True
    FONTS.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp())
    try:
        subprocess.run(["npm", "pack", "@fontsource/barlow-condensed@5.0.13", "--silent"], cwd=tmp,
                       check=True, capture_output=True, timeout=120)
        with tarfile.open(next(tmp.glob("*.tgz"))) as t:
            t.extractall(tmp, filter="data")
        for p in want:
            src = tmp / "package" / "files" / p.name
            if src.exists():
                shutil.copy(src, p)
    except Exception as e:  # no npm or no network: carry on with fallback fonts
        print(f"! couldn't fetch Barlow Condensed ({e}); headings will use a fallback font", file=sys.stderr)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return all(p.exists() for p in want)


def serve_dir(page, data, live, fonts_ok):
    d = Path(tempfile.mkdtemp(prefix="ppg-preview-"))
    html = site_document(page)  # no version stamp, so it never tries to reload itself
    if fonts_ok:
        (d / "_f").mkdir()
        for w, s in WEIGHTS:
            shutil.copy(FONTS / f"barlow-condensed-latin-{w}-{s}.woff2", d / "_f")
        ff = "".join(f'@font-face{{font-family:"Barlow Condensed";font-weight:{w};font-style:{s};'
                     f'src:url(_f/barlow-condensed-latin-{w}-{s}.woff2)}}' for w, s in WEIGHTS)
        html = html.replace("<style>", "<style>" + ff, 1)
    (d / "test.html").write_text(html, encoding="utf-8")
    for item in data.iterdir():
        if item.name in ("index.html", "live.json", "test.html", "_f", "preview-shots") or item.name.startswith("."):
            continue
        os.symlink(item, d / item.name)
    if live:
        j = json.loads(Path(live).read_text())
        j["date"] = dt.datetime.now(ZoneInfo(TZ)).date().isoformat()
        (d / "live.json").write_text(json.dumps(j))
    return d


def run(page, a, shots, label=""):
    """Load every tab/width/theme; return {shot_name: [flags]} and optionally save screenshots."""
    from playwright.sync_api import sync_playwright  # preinstalled in Claude's cloud workspace
    data = Path(a.data).resolve()
    asof = json.loads((data / "results.json").read_text())["asof"]
    d = serve_dir(page, data, a.live, ensure_fonts())
    handler = functools.partial(type("Q", (http.server.SimpleHTTPRequestHandler,),
                                     {"log_message": lambda *x: None}), directory=str(d))
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}/test.html"
    utc_day = dt.datetime.now(dt.timezone.utc).date().isoformat()  # the splash keys on the UTC date
    out, result = Path(a.out), {}
    try:
        with sync_playwright() as p:
            b = p.chromium.launch()
            for theme in a.themes.split(","):
                for w in [int(x) for x in a.widths.split(",")]:
                    ctx = b.new_context(viewport={"width": w, "height": 900}, device_scale_factor=2,
                                        is_mobile=w < 700, has_touch=w < 700, timezone_id=TZ,
                                        color_scheme="dark" if theme == "dark" else "light")
                    init = "localStorage.setItem('pool.theme','dark');" if theme == "toggle" else ""
                    if not a.fresh:
                        team = json.dumps(a.team)
                        init += (f"localStorage.setItem('pool.me',{json.dumps(team)});"
                                 "localStorage.setItem('pool.onboarded','true');"
                                 f"localStorage.setItem('pool.splash','{utc_day}');"
                                 f"localStorage.setItem('pool.ovn.'+{team},{json.dumps(json.dumps(asof))});")
                    ctx.add_init_script(init)
                    for tab in a.tabs.split(","):
                        pg, flags = ctx.new_page(), []

                        def expected(url):  # blocked web fonts, and no live.json unless --live was given
                            return "fonts.g" in url or (url.endswith("/live.json") and not a.live)

                        pg.on("console", lambda m, f=flags: m.type == "error"
                              and not m.text.startswith("Failed to load resource") and f.append("console: " + m.text[:140]))
                        pg.on("pageerror", lambda x, f=flags: f.append("error: " + str(x)[:140]))
                        pg.on("requestfailed", lambda r, f=flags: not expected(r.url)
                              and f.append("failed: " + r.url.split("/", 3)[-1][:80]))
                        pg.on("response", lambda r, f=flags: r.status >= 400 and not expected(r.url)
                              and f.append(f"missing ({r.status}): " + r.url.split("/", 3)[-1][:80]))
                        pg.goto(f"{base}#{tab}")
                        pg.wait_for_timeout(4500 if a.fresh else 1800)
                        # scroll through once so scroll-triggered reveals have run, then back to the top
                        pg.evaluate("async()=>{for(let y=0;y<document.body.scrollHeight;y+=600){scrollTo(0,y);"
                                    "await new Promise(r=>setTimeout(r,60))}scrollTo(0,0)}")
                        pg.wait_for_timeout(500)
                        o = pg.evaluate(OVERFLOW_JS)
                        if o["scrollW"] > o["clientW"]:
                            flags.append(f"page scrolls sideways ({o['scrollW']} > {o['clientW']})")
                        flags += ["poking past the edge: " + x for x in o["poking"][:6]]
                        name = f"{tab}-{w}-{theme}.png"
                        if shots:  # clip to the screen width: clipped overflow would otherwise widen the shot
                            hgt = pg.evaluate("document.documentElement.scrollHeight")
                            pg.screenshot(path=str(out / name), full_page=True,
                                          clip={"x": 0, "y": 0, "width": w, "height": hgt})
                        result[name] = flags
                        pg.close()
                    ctx.close()
            b.close()
    finally:
        srv.shutdown()
        shutil.rmtree(d, ignore_errors=True)
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("app")
    ap.add_argument("--compare")
    ap.add_argument("--data", default=str(ROOT))
    ap.add_argument("--live")
    ap.add_argument("--team", default="Lord of the Rinks")
    ap.add_argument("--tabs", default="today,race,mine,league,recap")
    ap.add_argument("--widths", default="390,1280")
    ap.add_argument("--themes", default="light,dark")
    ap.add_argument("--out", default="preview-shots")
    ap.add_argument("--fresh", action="store_true")
    a = ap.parse_args()
    bad = set(a.themes.split(",")) - {"light", "dark", "toggle"}
    if bad:
        sys.exit(f"Unknown theme(s): {', '.join(bad)}. Use light, dark and/or toggle.")

    page = bare_page(Path(a.app).read_text(encoding="utf-8"))
    before = run(bare_page(Path(a.compare).read_text(encoding="utf-8")), a, shots=False) if a.compare else {}
    Path(a.out).mkdir(parents=True, exist_ok=True)
    now = run(page, a, shots=True)

    new_problems = 0
    for name, flags in now.items():
        old = set(before.get(name, []))
        fresh = [f for f in flags if f not in old]
        new_problems += bool(fresh)
        mark = "!!" if fresh else ("ok" if not flags else "~~")
        print(f"{mark} {name}")
        for f in flags:
            print(f"     {f}{'  (already there)' if f in old else ''}")
    print(f"\n{len(now)} shots in {a.out}/. " + (f"{new_problems} with new problems." if new_problems
          else "No new problems." if a.compare else "No problems." if not any(now.values()) else ""))
    sys.exit(1 if new_problems else 0)


if __name__ == "__main__":
    main()
