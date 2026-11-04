import json, re, glob, sys, collections

SP = sys.argv[1]
pages = {}
for f in glob.glob(SP + "/pdf/out4/t1_*.json") + glob.glob(SP + "/pdf/out3/*.json"):
    for line in open(f, encoding="utf-8"):
        line = line.strip()
        if line: pages.update(json.loads(line))

def key(p):
    m = re.search(r"t(\d)/p-(\d+)\.png", p)
    return (int(m.group(1)), int(m.group(2)))

POSMAP = {"N": "n", "VT": "v", "VI": "v", "V": "v", "ADJ": "adj", "ADV": "adv", "PREP": "prep",
          "CONJ": "conj", "PRON": "pron", "DET": "det", "AUX": "v", "INT": "int", "SUF": None, "PRF": None, "ABBR": None, "SL": None,
          "ADY": "adv", "ABV": "adv", "YT": "v", "VV": "v", "I": "v", "CONS": "conj", "CON": "conj", "ABJ": "adj", "AJ": "adj", "PRE": "prep", "PRO": "pron"}
THAI = "฀-๿"

def clean_th(t):
    t = re.sub(rf"(?<=[{THAI}])\s+(?=[{THAI}])", "", t)
    t = re.sub(rf"(?<=[{THAI}])\s+(?=[{THAI}])", "", t)
    t = t.replace("ํา", "ำ").replace("ํ า", "ำ")
    t = re.sub(r"\s*\(\s*", " (", t); t = re.sub(r"\s*\)\s*", ") ", t)
    t = re.sub(r"\s+", " ", t).strip(" |_-—.,'\"")
    t = t.replace("( ", "(").replace(" )", ")")
    return t.strip()

def clean_pos(t):
    t = re.sub(r"[^A-Za-z]", "", t).upper()
    t = {"VL": "VI", "V1": "VI", "Vl": "VI", "ADI": "ADJ", "AD": "ADJ", "NN": "N", "PREF": "PREP"}.get(t, t)
    return t

def clean_word(t):
    t = t.strip().lower().replace("’", "'")
    t = re.sub(r"[^a-z' \-]", "", t)
    t = re.sub(r"\s+", " ", t).strip(" -'")
    return t

entries = []   # (test, word, senses)
unknown_pos = collections.Counter()
for p in sorted(pages, key=key):
    blocks = pages[p]
    if not isinstance(blocks, list): continue
    test = key(p)[0]
    for b in blocks:
        senses = []
        for pos, th in b["senses"]:
            P = clean_pos(pos)
            if P not in POSMAP: unknown_pos[P] += 1; continue
            th = clean_th(th)
            if th and POSMAP[P]: senses.append([POSMAP[P], th])
        w = clean_word(b["word"])
        if not w:
            if entries and entries[-1][0] == test: entries[-1][2].extend(senses)
            continue
        entries.append([test, w, senses])

import difflib
def dist1(a, b):
    if abs(len(a) - len(b)) > 1 or a == b: return False
    return difflib.SequenceMatcher(None, a, b).ratio() >= 0.88

entries = [e for e in entries if e[2] and 2 <= len(e[1]) and len(e[1].split()) <= 3 and (" " not in e[1] or all(len(t) >= 2 for t in e[1].split()))]
occ = collections.Counter(w for _, w, _ in entries)
# fold one-off English OCR typos into a close, more frequent spelling
fix = {}
common = [w for w, n in occ.items() if n >= 2]
for w, n in occ.items():
    if n == 1:
        c = [x for x in common if x[0] == w[0] and dist1(w, x)]
        pass  # folding disabled: it merged real words (factor/factory)
print("typo folds", len(fix), list(fix.items())[:15], file=sys.stderr)

bad = re.compile(r"[0-9a-zA-Z=@#%&*\[\]{}<>|~^]|^[^฀-๿]*$|[๐-๙]")
words = collections.OrderedDict()
for test, w, senses in entries:
    w = fix.get(w, w)
    e = words.setdefault(w, {"w": w, "t": [], "cnt": collections.Counter()})
    if test not in e["t"]: e["t"].append(test)
    for pos, th in senses:
        if bad.search(th) or len(th) < 2: continue
        e["cnt"][(pos, th)] += 1

out = []
for e in words.values():
    # cluster near-identical Thai senses (OCR variants) and keep the most frequent spelling
    reps = []
    for (pos, th), n in e["cnt"].most_common():
        for r in reps:
            if r[0] == pos and difflib.SequenceMatcher(None, r[1], th).ratio() >= 0.8:
                r[2] += n; break
        else: reps.append([pos, th, n])
    if not reps: continue
    cnt = collections.Counter()
    for pos, th, n in reps: cnt[pos] += n
    order = [p for p, _ in cnt.most_common()]
    reps.sort(key=lambda r: (order.index(r[0]), -r[2]))
    out.append({"w": e["w"], "p": order, "t": sorted(e["t"]), "s": [[p, th] for p, th, _ in reps]})
out.sort(key=lambda e: e["w"])
print("entries", len(entries), "unique", len(out), file=sys.stderr)
print("unknown pos", unknown_pos.most_common(15), file=sys.stderr)
print("per test", collections.Counter(e["t"][0] for e in out), file=sys.stderr)
json.dump(out, open(SP + "/ocr/words.json", "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
