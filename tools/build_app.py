"""Inject the word data into the flashcard app.

data/book-words.json      -> const BOOK = [...]   (OCR output from tools/build.py)
data/curated/*.tsv        -> const CUR = [...]    (proofread rows: word|pos|thai|example|family|cue)

Usage: python3 tools/build_app.py
"""
import glob, json, os, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "prototype", "vocab-cards.html")

book = json.load(open(os.path.join(ROOT, "data", "book-words.json"), encoding="utf-8"))
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

js = lambda v: json.dumps(v, ensure_ascii=False, separators=(",", ":"))
s = open(APP, encoding="utf-8").read()
s = re.sub(r"const BOOK = \[.*?\];\n", lambda m: f"const BOOK = {js(book)};\n", s, count=1, flags=re.S)
s = re.sub(r"const CUR = \[.*?\];\n", lambda m: f"const CUR = {js(cur)};\n", s, count=1, flags=re.S)
open(APP, "w", encoding="utf-8").write(s)
print(f"BOOK {len(book)} words, CUR {len(cur)} proofread rows -> {APP}")
