"""Inject the word data into the flashcard app.

data/book-words.json      -> const BOOK = [...]   (OCR output from tools/build.py)
data/curated/*.tsv        -> const CUR = [...]    (proofread rows: word|pos|thai|example|family|cue)

Usage: python3 tools/build_app.py
"""
import glob, json, os, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "prototype", "vocab-cards.html")

book = json.load(open(os.path.join(ROOT, "data", "book-words.json"), encoding="utf-8"))
# the OCR meanings are too noisy to show; keep only the word, its tests and its OCR part-of-speech order
book = [{"w": e["w"], "p": e["p"], "t": e["t"]} for e in book]
cur = []
for f in sorted(glob.glob(os.path.join(ROOT, "data", "curated", "*.tsv"))):
    for n, line in enumerate(open(f, encoding="utf-8"), 1):
        line = line.rstrip("\n")
        if not line.strip() or line.startswith("#"):
            continue
        row = line.split("|")
        if len(row) != 6:
            raise SystemExit(f"{f}:{n}: expected 6 fields, got {len(row)}")
        cur.append(row)

senses = []
for f in sorted(glob.glob(os.path.join(ROOT, "data", "senses", "*.tsv"))):
    for n, line in enumerate(open(f, encoding="utf-8"), 1):
        line = line.rstrip("\n")
        if not line.strip() or line.startswith("#"):
            continue
        row = line.split("|")
        if len(row) != 5:
            raise SystemExit(f"{f}:{n}: expected 5 fields, got {len(row)}")
        senses.append(row)

js = lambda v: json.dumps(v, ensure_ascii=False, separators=(",", ":"))
s = open(APP, encoding="utf-8").read()
s = re.sub(r"const BOOK = \[.*?\];\n", lambda m: f"const BOOK = {js(book)};\n", s, count=1, flags=re.S)
s = re.sub(r"const CUR = \[.*?\];\n", lambda m: f"const CUR = {js(cur)};\n", s, count=1, flags=re.S)
s = re.sub(r"const SENSES = \[.*?\];\n", lambda m: f"const SENSES = {js(senses)};\n", s, count=1, flags=re.S)
open(APP, "w", encoding="utf-8").write(s)
print(f"BOOK {len(book)} words, CUR {len(cur)} proofread rows, SENSES {len(senses)} rows -> {APP}")

# Standalone site for Cloudflare (public/index.html): the artifact file has no document skeleton, so add one.
HEAD = """<!doctype html>
<html lang="th">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#FFFFFF">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="mobile-web-app-capable" content="yes">
<style>
:root { color-scheme: light; padding-top: env(safe-area-inset-top, 0px); padding-bottom: env(safe-area-inset-bottom, 0px); box-sizing: border-box; height: 100%; }
body { margin: 0; font: 14px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; }
img { max-width: 100%; }
[hidden] { display: none !important; }
</style>
"""
title_end = s.index("</title>") + len("</title>")
page = HEAD + s[:title_end] + "\n" + s[title_end:].replace("<div class=\"app\"", "</head>\n<body>\n<div class=\"app\"", 1) + "\n</body>\n</html>\n"
os.makedirs(os.path.join(ROOT, "public"), exist_ok=True)
open(os.path.join(ROOT, "public", "index.html"), "w", encoding="utf-8").write(page)
print("site -> public/index.html")
