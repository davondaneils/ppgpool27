"""Assemble the folder GitHub Pages serves: the live site at the root, plus one preview copy per preview branch.

Run by .github/workflows/site.yml from a checkout of main, after scripts/live.py:
    python scripts/stage_site.py _site

- The live site is main as it stands (minus git and workflow files), served at https://ppgpool.com/.
- Every branch named preview/<name> is served at https://ppgpool.com/preview/<name>/ with today's real
  data: its results.json and live.json are replaced by main's, so a preview only differs in the app itself.
- Preview pages are kept out of search results and get a PREVIEW tag, and their saved settings live apart
  from the live app's (they start from your team, rivals and theme), so trying a preview never changes
  what the live app remembers.
"""
import re
import shutil
import subprocess
import sys
from pathlib import Path

SKIP = {".git", ".github", "_site", "tools", "scripts", "preview-shots", "__pycache__"}
DATA = ("results.json", "live.json")

# Runs before the app: keeps the preview's localStorage apart from the live app's (same domain, so they
# would otherwise share it), seeded once from the live app's team, rivals, theme and onboarding.
SHIM = """<script>(function(){try{var L=window.localStorage,P="pv.",S=Storage.prototype,g=S.getItem,s=S.setItem,r=S.removeItem;
if(g.call(L,P+"pool.me")===null){["pool.me","pool.stars","pool.onboarded","pool.theme"].forEach(function(k){var v=g.call(L,k);if(v!==null)s.call(L,P+k,v)})}
S.getItem=function(k){return g.call(this,this===L?P+k:k)};S.setItem=function(k,v){return s.call(this,this===L?P+k:k,v)};
S.removeItem=function(k){return r.call(this,this===L?P+k:k)}}catch(e){}})();</script>
<meta name="robots" content="noindex,nofollow">
"""

TAG = """<div aria-hidden="true" style="position:fixed;top:env(safe-area-inset-top);left:50%;transform:translateX(-50%);z-index:2147483647;pointer-events:none;background:#d7332b;color:#fff;font:700 8px/1 Inter,system-ui,sans-serif;letter-spacing:.14em;padding:2px 7px 3px;border-radius:0 0 6px 6px;opacity:.92">PREVIEW</div>
"""


def git(*args):
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True).stdout


def copy_live(out):
    for p in Path(".").iterdir():
        if p.name in SKIP:
            continue
        dest = out / p.name
        shutil.copytree(p, dest) if p.is_dir() else shutil.copy2(p, dest)


def preview_branches():
    git("fetch", "--depth=1", "origin", "+refs/heads/preview/*:refs/remotes/origin/preview/*")
    refs = git("for-each-ref", "--format=%(refname:short)", "refs/remotes/origin/preview/").split()
    return [r for r in refs if r.startswith("origin/preview/")]


def mark_preview(page, name):
    s = page.read_text(encoding="utf-8")
    reset = "<style>body{margin:0;padding:0}img{max-width:100%}</style>\n"  # added by tools/build_site.py
    s = s.replace(reset, reset + SHIM, 1) if reset in s else s.replace("<head>\n", "<head>\n" + SHIM, 1)
    s = s.replace("<title>", f"<title>Preview {name} · ", 1)
    s = re.sub(r"<body>", "<body>\n" + TAG, s, count=1)
    page.write_text(s, encoding="utf-8")


def main():
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "_site")
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir()
    copy_live(out)
    names = []
    for ref in preview_branches():
        name = ref.split("/", 2)[2]
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,40}", name):
            print(f"skipping {ref}: preview names are lowercase letters, digits and dashes")
            continue
        dest = out / "preview" / name
        dest.mkdir(parents=True)
        tar = subprocess.run(["git", "archive", ref], check=True, capture_output=True).stdout
        subprocess.run(["tar", "-x", "-C", str(dest)], input=tar, check=True)
        for d in SKIP:
            shutil.rmtree(dest / d, ignore_errors=True)
        for f in DATA:
            (dest / f).unlink(missing_ok=True)
            if Path(f).exists():
                shutil.copy2(f, dest / f)
        if (dest / "index.html").exists():
            mark_preview(dest / "index.html", name)
        names.append(name)
    (out / "robots.txt").write_text("User-agent: *\nDisallow: /preview/\n", encoding="utf-8")
    print("live site staged; previews:", ", ".join(names) or "none")


if __name__ == "__main__":
    main()
