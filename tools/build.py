#!/usr/bin/env python3
"""Builds the mod pack site into _site/ from the packs/ folder."""
import html
import shutil
import struct
import sys
import tomllib
import zipfile
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "_site"
GAME = "https://www.kylejameswalker.com/last-harvest/"
REPO = "https://github.com/KyleJamesWalker/last-harvest-packs"
CARD_PX = 96
PROP_PX = 64
KINDS = {"enemies/": "enemy", "players/": "player", "props/": "prop"}
WHOLE = {"props.txt", "ground.txt", "farm.txt", "powerups.txt", "enemies.txt"}


def png_info(data):
    """Returns the size and the text chunks of a PNG."""
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG")
    pos, size, text = 8, None, {}
    while pos < len(data):
        length, kind = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + length]
        pos += 12 + length
        if kind == b"IHDR":
            size = struct.unpack(">II", body[:8])
        elif kind == b"tEXt":
            key, _, value = body.partition(b"\0")
            text[key.decode("latin-1")] = value.decode("latin-1")
        elif kind == b"iTXt":
            key, _, rest = body.partition(b"\0")
            compressed = rest[0] == 1
            _lang, _, rest = rest[2:].partition(b"\0")
            _translated, _, value = rest.partition(b"\0")
            text[key.decode("latin-1")] = (zlib.decompress(value) if compressed else value).decode("utf-8")
    if size is None:
        raise ValueError("no IHDR")
    return size, text


def fields(text):
    """Reads a card's [id] section as a dict of its first word to the rest of the line."""
    out = {}
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if line.startswith("["):
            out["id"] = line.strip("[]")
        elif line:
            key, _, value = line.partition(" ")
            out.setdefault(key, value.strip())
    return out


def card(path, data):
    """Describes a card or prop: its name, text and the frames the page animates."""
    kind = next(k for p, k in KINDS.items() if path.startswith(p))
    (width, height), text = png_info(data)
    info = fields(text.get(f"last-harvest-{kind}", ""))
    detail = int(text.get("last-harvest-detail", "1").strip() or 1)
    if kind == "prop":
        frames = int(info.get("frames", 1))
        fw = width // frames
        fh = height - int(info.get("views", 0) or 0)
        row, shown = 0, frames
    else:
        walk = int(info.get("walk", 3))
        rows = int(text.get("last-harvest-rows", "5").strip() or 5)
        fw, fh = width // max(walk, 3), height // rows
        # The player is seen from behind all run, so show the back walk.
        row, shown = (2 if kind == "player" else 0), walk
    target = PROP_PX if kind == "prop" else CARD_PX
    scale = max(1, target * detail // max(fw, fh)) / detail
    return {
        "kind": kind, "file": path, "id": info.get("id", Path(path).name.split(".")[0]),
        "name": info.get("name") or info.get("id", "").replace("_", " ").title(),
        "about": info.get("about", ""), "w": fw * scale, "h": fh * scale, "sheet": (width * scale, height * scale),
        "y": row * fh * scale, "frames": shown,
    }


def read_pack(folder):
    meta = tomllib.loads((folder / "pack.toml").read_text())
    for key in ("title", "author", "game", "summary"):
        if not meta.get(key):
            raise ValueError(f"{folder.name}/pack.toml has no {key}")
    paks = sorted(folder.glob("*.pak"))
    if len(paks) != 1:
        raise ValueError(f"{folder.name} holds {len(paks)} .pak files, not 1")
    with zipfile.ZipFile(paks[0]) as z:
        names = z.namelist()
        manifest = tomllib.loads(z.read("manifest.toml").decode())
        if "format" not in manifest:
            raise ValueError(f"{paks[0].name}: manifest.toml has no format")
        cards = [card(n, z.read(n)) for n in sorted(names) if n.endswith(".png") and any(n.startswith(p) for p in KINDS)]
        art = {c["file"]: z.read(c["file"]) for c in cards}
    return {
        "slug": folder.name, "meta": meta, "pak": paks[0], "cards": cards, "art": art,
        "sounds": sorted(Path(n).name for n in names if n.startswith("sounds/") and not n.endswith("/")),
        "data": sorted(n for n in names if "/" not in n and n.endswith(".txt")),
        "shots": sorted((folder / "shots").glob("*.jpg")),
    }


def e(s):
    return html.escape(str(s), quote=True)


def px(n):
    return f"{n:g}px"


def head(title, extra_css=""):
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'self'; style-src 'unsafe-inline'; object-src 'none'; base-uri 'none'">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{e(title)}</title>
<style>
{STYLE}
{extra_css}
</style>
</head>
<body>
"""


FOOT = f"""<footer><p>Make your own pack in the <a href="{GAME}editor/">card editor</a> and share it with a pull request to
<a href="{REPO}">last-harvest-packs</a>.</p></footer>
</body>
</html>
"""

INSTALL = f"""<h3>Install</h3>
<ol>
  <li><b>Handheld or desktop:</b> copy the <code>.pak</code> into the <code>data/mods/</code> folder beside <code>game_data.pak</code>, then restart the game.</li>
  <li><b>Android:</b> copy it into <code>mods/</code> in the game folder that Settings &gt; Game folder chose.</li>
  <li><b>Browser:</b> open <a href="{GAME}play/">the web game</a>, press Add mod and pick the <code>.pak</code>.</li>
</ol>
<p class="small">The game loads packs in file name order. Stats shows how many loaded, and the title screen names a pack it skipped.</p>
"""


def download(p):
    size = p["pak"].stat().st_size
    return f'<a class="get" href="{e(p["pak"].name)}" download>Download <span>{e(p["pak"].name)} · {size / 1024:.0f} KB</span></a>'


def render_index(packs):
    tiles = []
    for p in packs:
        m, slug = p["meta"], p["slug"]
        thumb = f'<img src="packs/{slug}/shots/{p["shots"][0].name}" alt="" loading="lazy">' if p["shots"] else '<div class="noshot"></div>'
        count = len(p["cards"])
        tiles.append(
            f'<li><a href="packs/{e(slug)}/">{thumb}<div><b>{e(m["title"])}</b>'
            f'<small>by {e(m["author"])} · {e(m["game"])} · {count} card{"s" if count != 1 else ""}</small>'
            f'<span>{e(m["summary"])}</span></div></a></li>'
        )
    return (head("Last Harvest mod packs")
            + f"""<h1>Mod packs</h1>
<p>Mod packs for <a href="{GAME}">Last Harvest</a>. Each pack is one <code>.pak</code> file that changes the game's zombies,
players, art, sounds or rules. Pick a pack for its details and download.</p>
<ul class="packs">{''.join(tiles)}</ul>
""" + FOOT)


def render_pack(p):
    m = p["meta"]
    css, cards = [], []
    for i, c in enumerate(p["cards"]):
        cls = f"s{i}"
        sw, sh = c["sheet"]
        css.append(
            f".{cls} {{ width: {px(c['w'])}; height: {px(c['h'])}; background: url('{c['file']}') 0 -{px(c['y'])} / "
            f"{px(sw)} {px(sh)}; animation: {cls} {c['frames'] * 0.18:.2f}s steps({c['frames']}) infinite; }}\n"
            f"@keyframes {cls} {{ to {{ background-position-x: -{px(c['w'] * c['frames'])}; }} }}"
        )
        about = f"<p>{e(c['about'])}</p>" if c["about"] else ""
        cards.append(
            f'<li><div class="sprite {cls}" role="img" aria-label="{e(c["name"])}"></div>'
            f"<div><b>{e(c['name'])}</b> <small>{e(c['kind'])}</small>{about}</div></li>"
        )
    shots = "".join(
        f'<a href="shots/{s.name}"><img src="shots/{s.name}" alt="{e(m["title"])} screenshot {n}" loading="lazy"></a>'
        for n, s in enumerate(p["shots"], 1)
    )
    changes = "".join(f"<li>{e(x)}</li>" for x in m.get("changes", []))
    whole = [d for d in p["data"] if d in WHOLE]
    note = ""
    if whole:
        files = ", ".join(f"<code>{e(d)}</code>" for d in whole)
        note = f'<p class="small">Replaces the whole of {files}. A second pack that replaces the same file overrides this one, by file name order.</p>'
    sounds = ""
    if p["sounds"]:
        sounds = '<p class="small">Sounds: ' + ", ".join(f"<code>{e(s)}</code>" for s in p["sounds"]) + "</p>"
    return (head(f"{m['title']} · Last Harvest mod packs", "\n".join(css))
            + f"""<p class="back"><a href="../../">← All mod packs</a></p>
<div class="head"><div><h1>{e(m['title'])}</h1><p class="by">by {e(m['author'])} · made for {e(m['game'])}</p></div>
{download(p)}</div>
<p>{e(m['summary'])}</p>
<div class="shots">{shots}</div>
{f'<h3>What it changes</h3><ul class="changes">{changes}</ul>' if changes else ''}
<h3>Cards</h3>
<ul class="cards">{''.join(cards)}</ul>
{note}{sounds}
{INSTALL}""" + FOOT)


STYLE = """  html { background: #19191e; color: #ebebf2; }
  body { margin: 0 auto; max-width: 760px; padding: 48px 16px calc(32px + env(safe-area-inset-bottom));
         font: 17px/1.5 -apple-system, system-ui, sans-serif; }
  h1 { margin: 0 0 8px; font-size: 40px; letter-spacing: 0.04em; color: #f2bf4d; }
  h3 { margin: 32px 0 8px; font-size: 20px; color: #f2bf4d; }
  p { margin: 0 0 16px; color: #c8c8d2; }
  a { color: #f2bf4d; }
  code { font-size: 14px; color: #ebebf2; }
  .back { margin-bottom: 24px; font-size: 15px; }
  .packs { display: grid; gap: 12px; margin: 32px 0; padding: 0; list-style: none; }
  @media (min-width: 560px) { .packs { grid-template-columns: 1fr 1fr; } }
  .packs a { display: flex; gap: 12px; align-items: center; height: 100%; box-sizing: border-box; padding: 12px;
             border-radius: 12px; background: #26262d; color: inherit; text-decoration: none; }
  .packs a:hover, .packs a:focus-visible { background: #3d3d47; }
  .packs img, .packs .noshot { flex: none; width: 88px; height: 88px; border-radius: 8px; object-fit: cover; background: #1f1f25; }
  .packs b { display: block; font-size: 20px; color: #f2bf4d; }
  .packs small { display: block; font-size: 13px; color: #8c8c99; }
  .packs span { display: block; margin-top: 4px; font-size: 14px; line-height: 1.4; color: #c8c8d2; }
  .head { display: flex; flex-wrap: wrap; gap: 16px; justify-content: space-between; align-items: center; margin-bottom: 12px; }
  .head h1 { margin: 0; }
  .by { margin: 0; font-size: 15px; }
  .get { padding: 10px 18px; border-radius: 10px; background: #f2bf4d; color: #19191e; font-weight: 700; text-decoration: none; }
  .get:hover, .get:focus-visible { background: #ffd77a; }
  .get span { display: block; font-size: 13px; font-weight: 400; }
  .shots { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin: 0 0 16px; }
  .shots img { display: block; width: 100%; aspect-ratio: 1; object-fit: cover; border-radius: 6px; }
  .changes { margin: 0 0 16px; padding-left: 20px; color: #c8c8d2; }
  .cards { display: grid; gap: 12px; margin: 0 0 16px; padding: 0; list-style: none; }
  @media (min-width: 560px) { .cards { grid-template-columns: 1fr 1fr; } }
  .cards li { display: flex; gap: 12px; align-items: center; padding: 12px; border-radius: 10px; background: #26262d; }
  .cards p { margin: 4px 0 0; font-size: 14px; }
  .cards small { color: #8c8c99; }
  .sprite { flex: none; image-rendering: pixelated; background-repeat: no-repeat; }
  @media (prefers-reduced-motion: reduce) { .sprite { animation: none !important; } }
  .small { font-size: 14px; }
  ol { padding-left: 20px; color: #c8c8d2; }
  footer { margin-top: 48px; }"""


def main():
    packs = [read_pack(f) for f in sorted((ROOT / "packs").iterdir()) if f.is_dir()]
    shutil.rmtree(OUT, ignore_errors=True)
    for p in packs:
        dest = OUT / "packs" / p["slug"]
        (dest / "shots").mkdir(parents=True)
        shutil.copy2(p["pak"], dest / p["pak"].name)
        for s in p["shots"]:
            shutil.copy2(s, dest / "shots" / s.name)
        for name, data in p["art"].items():
            (dest / name).parent.mkdir(parents=True, exist_ok=True)
            (dest / name).write_bytes(data)
        (dest / "index.html").write_text(render_pack(p))
    (OUT / "index.html").write_text(render_index(packs))
    (OUT / ".nojekyll").write_text("")
    print(f"built {OUT} with {len(packs)} pack(s)")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, zipfile.BadZipFile) as err:
        sys.exit(f"build failed: {err}")