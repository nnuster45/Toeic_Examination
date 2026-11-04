import os, sys, json, subprocess, io, csv
from PIL import Image
import numpy as np

def tsv(img, lang, psm=6):
    buf = io.BytesIO(); img.save(buf, format="PNG")
    out = subprocess.run(["tesseract", "stdin", "stdout", "-l", lang, "--psm", str(psm), "tsv"],
                         input=buf.getvalue(), capture_output=True).stdout.decode("utf-8", "ignore")
    lines = {}
    for r in csv.DictReader(io.StringIO(out), delimiter="\t", quoting=csv.QUOTE_NONE):
        if r["level"] != "5" or not r["text"].strip(): continue
        k = (r["block_num"], r["par_num"], r["line_num"])
        L = lines.setdefault(k, {"y": [], "t": []})
        L["y"].append(int(r["top"]) + int(r["height"]) / 2); L["t"].append(r["text"])
    res = [(sum(L["y"]) / len(L["y"]), " ".join(L["t"])) for L in lines.values()]
    return sorted(res)

def page(path):
    im = Image.open(path).convert("L")
    W, H = im.size
    a = np.array(im).astype(int)
    sx = W / 1240
    # header band
    left = a[:, int(72*sx):int(110*sx)].mean(1)
    dark = [i for i in range(len(left)) if left[i] < 80]
    if not dark: return None
    top = max(i for i in dark if i < dark[0] + 120) + 3
    seps = [top]
    for i in range(top + 5, H):
        if left[i] < 238 and a[i, int(1130*sx):int(1168*sx)].mean() < 238 and i - seps[-1] > 15:
            seps.append(i)
    seps.append(H)
    S = 2
    def col(x0, x1):
        c = im.crop((int(x0*sx), top, int(x1*sx), H))
        return c.resize((c.width*S, c.height*S), Image.LANCZOS)
    words = tsv(col(225, 470), "eng")
    nums = tsv(col(70, 225), "eng")
    pos = tsv(col(462, 700), "eng")
    mean = tsv(col(700, 1175), "tha")
    if (len(seps) <= 3 or os.environ.get("GAP")) and len(pos) > 1:
        # no ruled separators: split where the gap between POS lines is clearly bigger than normal line spacing
        ys = [y for y, _ in pos]
        gaps = sorted(b - a for a, b in zip(ys, ys[1:]))
        base = gaps[len(gaps) // 4] if gaps else 0
        cuts = [top]
        for a, b in zip(ys, ys[1:]):
            if b - a > base * 1.55: cuts.append(int((a + b) / 2 / S + top))
        seps = cuts + [H]
    def blk(y): 
        y = y / S + top
        for j in range(len(seps) - 1):
            if seps[j] <= y < seps[j+1]: return j
        return len(seps) - 2
    blocks = [{"num": "", "word": "", "senses": []} for _ in range(len(seps) - 1)]
    for y, t in words: blocks[blk(y)]["word"] += (" " if blocks[blk(y)]["word"] else "") + t
    for y, t in nums: blocks[blk(y)]["num"] += t
    ml = list(mean)
    for y, t in pos:
        # nearest meaning line
        best = min(ml, key=lambda m: abs(m[0] - y)) if ml else None
        th = best[1] if best and abs(best[0] - y) < 25 * S else ""
        blocks[blk(y)]["senses"].append([t, th])
    return [b for b in blocks if b["word"] or b["senses"]]

if __name__ == "__main__":
    out = {}
    for p in sys.argv[1:]:
        try: out[p] = page(p)
        except Exception as e: out[p] = {"error": str(e)}
    print(json.dumps(out, ensure_ascii=False))
