"""Build the website's index.html from the app page that lives on the artifact.

Usage (from the repo root):
    python3 tools/build_site.py PATH/TO/app/index.html

Pass the app page as the artifact holds it. Both forms work:
  - the page as an Artifact read returns it (wrapped in the artifact host's <html>/<head> skeleton), or
  - the bare page (starts with <title>, no skeleton).
Passing the built website index.html is refused, so it can't be wrapped twice.

The script makes the link-preview image URLs absolute (so group-chat previews work), wraps the page in
a full document, adds a version stamp so copies people already have open reload themselves after a
deploy, and writes index.html and version.json in the repo root. Nothing else in the repo is touched.
"""
import sys
import time
from pathlib import Path

SITE = "https://davondaneils.github.io/ppgpool27/"
ROOT = Path(__file__).resolve().parent.parent


def bare_page(text):
    """Return the bare app page from either the bare file or the artifact host's wrapped copy."""
    if "window.APPV=" in text:
        raise SystemExit("That's the built website page. Pass the artifact's index.html instead.")
    head = text[:400].lower()
    if head.startswith("<!doctype"):
        start = text.find("<body>")
        end = text.rfind("</body>")
        if start < 0 or end < 0:
            raise SystemExit("Couldn't find the page inside the artifact skeleton.")
        text = text[start + len("<body>"):end].strip("\n") + "\n"
    if not text.lstrip().startswith("<title>"):
        raise SystemExit("This doesn't look like the PPGPool27 app page (it should start with <title>).")
    return text


def site_document(bare, version=None):
    """Wrap the bare page as the website serves it."""
    s = bare
    for old, new in [('<meta property="og:image" content="og.png">',
                      f'<meta property="og:image" content="{SITE}og.png">\n<meta property="og:url" content="{SITE}">'),
                     ('<meta name="twitter:image" content="og.png">',
                      f'<meta name="twitter:image" content="{SITE}og.png">')]:
        if old in s:
            s = s.replace(old, new, 1)
        else:
            print(f"! link-preview tag not found, previews may break: {old}", file=sys.stderr)
    cut = s.index("</style>") + len("</style>")  # title, meta, fonts and CSS are head material
    refresh = ""
    if version:
        refresh = ('<script>window.APPV="%s";(function(){var busy=false;function chk(){if(busy)return;busy=true;'
                   'fetch("version.json?"+Date.now(),{cache:"no-store"}).then(function(r){return r.ok?r.json():null})'
                   '.then(function(j){busy=false;if(j&&j.v&&j.v!==window.APPV){try{if(sessionStorage.getItem("ppg.rl")===j.v)return;'
                   'sessionStorage.setItem("ppg.rl",j.v)}catch(e){}location.reload()}}).catch(function(){busy=false})}'
                   'addEventListener("load",function(){setTimeout(chk,1500)});document.addEventListener("visibilitychange",'
                   'function(){if(document.visibilityState==="visible")chk()})})();</script>\n') % version
    # The artifact host puts a small reset in front of the page; the app relies on it (without
    # body{margin:0} the whole site gets 8 px grey gutters), so the website carries the same reset.
    return ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
            '<style>body{margin:0;padding:0}img{max-width:100%}</style>\n'
            + s[:cut] + "\n" + refresh + "</head>\n<body>" + s[cut:] + "\n</body>\n</html>\n")


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    bare = bare_page(Path(sys.argv[1]).read_text(encoding="utf-8"))
    v = str(int(time.time()))
    out = site_document(bare, v)
    (ROOT / "index.html").write_text(out, encoding="utf-8")
    (ROOT / "version.json").write_text('{"v":"%s"}' % v, encoding="utf-8")
    print(f"index.html built ({len(out):,} bytes), version {v}")


if __name__ == "__main__":
    main()
