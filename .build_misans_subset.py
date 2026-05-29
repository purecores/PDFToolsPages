#!/usr/bin/env python3
# Regenerate the local MiSans subset fonts.
#
# Run this whenever you ADD new Chinese/Latin text to index.html, so the local
# subset keeps covering every glyph the UI renders.
#
#   python .build_misans_subset.py
#
# It will:
#   1. read every character that appears in index.html,
#   2. download only the MiSans chunks that contain those characters (jsDelivr),
#   3. merge + re-subset them into assets/fonts/misans-{400,500,600,700}.woff2,
#   4. print the `unicode-range:` string to paste into the @font-face rules in
#      index.html (glyphs outside it fall through to system fonts).
#
# No CDN is used at runtime: these local woff2 are the only web font; if a local
# file fails to load the browser uses the system fonts in the stack.
#
# Requires: fonttools + (brotli or brotlicffi).  CDN access to jsdelivr.

import os, re, io, urllib.request
from fontTools.ttLib import TTFont
from fontTools.merge import Merger
from fontTools.subset import Subsetter, Options

JSDELIVR = "https://cdn.jsdelivr.net/npm/misans@4.1.0/lib/Normal"
WEIGHTS = {"Regular": 400, "Medium": 500, "Semibold": 600, "Bold": 700}
OUT = "assets/fonts"
CACHE = ".misans_cache"
os.makedirs(OUT, exist_ok=True)
os.makedirs(CACHE, exist_ok=True)


def fetch(url, binary=True):
    fn = os.path.join(CACHE, re.sub(r"[^A-Za-z0-9._-]", "_", url.split("/")[-1]))
    if os.path.exists(fn) and os.path.getsize(fn) > 0:
        return open(fn, "rb").read() if binary else open(fn, encoding="utf-8").read()
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    data = urllib.request.urlopen(req, timeout=60).read()
    open(fn, "wb").write(data)
    return data if binary else data.decode("utf-8")


def expand(ur):
    cps = set()
    for tok in ur.split(","):
        tok = tok.strip().replace("U+", "").replace("u+", "")
        if "-" in tok:
            a, b = tok.split("-"); cps.update(range(int(a, 16), int(b, 16) + 1))
        elif tok:
            cps.add(int(tok, 16))
    return cps


def to_ranges(cps):
    cps = sorted(cps); out = []; s = p = cps[0]
    for c in cps[1:]:
        if c == p + 1: p = c
        else: out.append((s, p)); s = p = c
    out.append((s, p))
    return ",".join(f"U+{a:04x}" if a == b else f"U+{a:04x}-{b:04x}" for a, b in out)


# 1) characters used anywhere in index.html (covers HTML text + JS string literals)
src = open("index.html", encoding="utf-8").read()
want = sorted({ord(c) for c in src if ord(c) >= 0x20 and c != "﻿"})
print("unique codepoints in index.html:", len(want))

# 2) chunk index -> unicode-range (chunking identical across weights)
css = fetch(f"{JSDELIVR}/MiSans-Regular.min.css", binary=False)
chunk_ur = {int(i): ur.strip() for i, ur in
            re.findall(r"url\('MiSans-Regular\.(\d+)\.woff2'\)[^}]*?unicode-range:([^;]+);", css)}
wantset = set(want)
needed = sorted(i for i, ur in chunk_ur.items() if expand(ur) & wantset)
covered = set().union(*(expand(chunk_ur[i]) for i in needed)) if needed else set()
missing = wantset - covered
print(f"needed chunks: {len(needed)}  covered {len(wantset & covered)}/{len(wantset)}")
if missing:
    print("NOT in MiSans (will use system fonts):", " ".join(chr(c) for c in sorted(missing)))

# 3) per weight: merge needed chunks, subset to exact charset -> woff2
for wname, wval in WEIGHTS.items():
    paths = []
    for i in needed:
        raw = fetch(f"{JSDELIVR}/MiSans-{wname}.{i}.woff2", binary=True)
        p = os.path.join(CACHE, f"MiSans-{wname}.{i}.ttf")
        TTFont(io.BytesIO(raw)).save(p)
        paths.append(p)
    merged = TTFont(paths[0]) if len(paths) == 1 else Merger().merge(paths)
    opt = Options(); opt.flavor = "woff2"; opt.desubroutinize = True
    opt.name_IDs = ["*"]; opt.name_legacy = True; opt.name_languages = ["*"]
    opt.layout_features = ["*"]; opt.notdef_outline = True; opt.recalc_bounds = True
    ss = Subsetter(options=opt); ss.populate(unicodes=want); ss.subset(merged)
    out = os.path.join(OUT, f"misans-{wval}.woff2")
    merged.flavor = "woff2"; merged.save(out)
    print(f"{wname}({wval}) -> {out}  {os.path.getsize(out)} bytes")

# 4) unicode-range to paste into the @font-face rules in index.html
print("\n--- paste this as `unicode-range:` in each MiSans @font-face in index.html ---")
print(to_ranges(want) + ";")
