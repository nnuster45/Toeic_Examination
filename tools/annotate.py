"""Annotate every example sentence with its structure, tense and the role of the target word.

Reads   data/curated/*.tsv, data/senses/*.tsv and the themed WORDS inside prototype/vocab-cards.html
Writes  data/annotations.json  =  { sentence: { "g": [[text, role], ...], "t": tense, "p": passive, "r": { word: [pos, reason] } } }

Roles: S subject, V verb, O object, C complement, M modifier / adverbial, "" punctuation.
Needs:  pip install spacy && python3 -m spacy download en_core_web_md
Usage:  python3 tools/annotate.py   (then python3 tools/build_app.py)
"""
import glob, json, os, re
import spacy

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
nlp = spacy.load("en_core_web_md")

POS_EN = {"n": "Noun", "v": "Verb", "adj": "Adjective", "adv": "Adverb", "prep": "Preposition", "conj": "Conjunction", "pron": "Pronoun"}
POS_TH = {"n": "คำนาม", "v": "คำกริยา", "adj": "คุณศัพท์", "adv": "กริยาวิเศษณ์", "prep": "บุพบท", "conj": "คำสันธาน", "pron": "สรรพนาม"}
SPACY2POS = {"NOUN": "n", "PROPN": "n", "VERB": "v", "AUX": "v", "ADJ": "adj", "ADV": "adv", "ADP": "prep",
             "SCONJ": "conj", "CCONJ": "conj", "PRON": "pron", "DET": "adj", "NUM": "adj", "PART": "adv"}
LINKING = {"be", "become", "remain", "seem", "stay", "look", "appear", "sound", "feel", "get", "keep", "prove", "turn"}
ROLE_TH = {"S": "ประธาน", "O": "กรรม", "C": "ส่วนเติมเต็ม", "M": "ส่วนขยาย", "V": "กริยา"}

S_DEPS = {"nsubj", "nsubjpass", "csubj", "csubjpass", "expl"}
V_DEPS = {"aux", "auxpass", "neg", "prt"}
O_DEPS = {"dobj", "iobj", "dative", "obj", "ccomp"}
C_DEPS = {"acomp", "attr", "oprd"}


# ---------------------------------------------------------------- inputs
def rows(pattern, n):
    for f in sorted(glob.glob(os.path.join(ROOT, pattern))):
        for line in open(f, encoding="utf-8"):
            line = line.rstrip("\n")
            if line.strip() and not line.startswith("#"):
                r = line.split("|")
                if len(r) == n:
                    yield r


def fix_pos(p):
    return "adj" if p == "det" else p


jobs = {}  # sentence -> {word: [candidate pos list]}
def add(sentence, word, cands):
    if sentence:
        jobs.setdefault(sentence, {}).setdefault(word, [])
        for c in cands:
            if c in POS_EN and c not in jobs[sentence][word]:
                jobs[sentence][word].append(c)

for r in rows("data/curated/*.tsv", 6):
    add(r[3], r[0].split("=")[-1], [fix_pos(p) for p in r[1].split(",")])
for r in rows("data/senses/*.tsv", 5):
    add(r[4], r[0], [fix_pos(r[1])])
html = open(os.path.join(ROOT, "prototype", "vocab-cards.html"), encoding="utf-8").read()
for m in re.finditer(r'\{ d:"[a-z]+", w:"([^"]+)", p:\[([^\]]*)\].*?ex:"([^"]+)"', html):
    add(m.group(3), m.group(1), re.findall(r'"(\w+)"', m.group(2)))


# ---------------------------------------------------------------- structure
def label(tok, roles, role):
    for t in tok.subtree:
        roles[t.i] = role


def label_clause(head, roles):
    """Label one clause: head verb + aux as V, its arguments as S/O/C, everything else as M."""
    roles[head.i] = "V"
    for ch in head.children:
        d = ch.dep_
        if d == "punct":
            continue
        if d in S_DEPS:
            label(ch, roles, "S")
        elif d in V_DEPS:
            label(ch, roles, "V")
        elif d in O_DEPS and not (d == "ccomp" and ch.i < head.i):
            label(ch, roles, "O")
        elif d in C_DEPS:
            label(ch, roles, "C")
        elif d == "xcomp":
            label(ch, roles, "C" if ch.pos_ == "ADJ" else "O")
        elif d == "conj" and ch.pos_ in ("VERB", "AUX"):
            label_clause(ch, roles)  # second predicate: "... and helps ..."
        else:
            label(ch, roles, "M")


def tense_of(root):
    if root.pos_ not in ("VERB", "AUX"):
        return None, False
    aux = [c for c in root.children if c.dep_ in ("aux", "auxpass")]
    subj = [c for c in root.children if c.dep_ in S_DEPS]
    passive = any(c.dep_ == "auxpass" for c in aux) or any(c.dep_ == "nsubjpass" for c in subj)
    words = [a.lower_ for a in aux]
    tags = [a.tag_ for a in aux]
    modal = next((a.lower_ for a in aux if a.tag_ == "MD"), None)
    if not subj and root.tag_ == "VB" and not aux:
        return "Imperative", passive
    if root.lemma_ == "go" and root.tag_ == "VBG" and any(c.dep_ == "xcomp" for c in root.children):
        return "Future (be going to)", passive
    perfect = any(w in ("have", "has", "had", "'ve") for w in words) and (root.tag_ == "VBN" or "been" in words)
    cont = root.tag_ == "VBG" and any(w in ("am", "is", "are", "was", "were", "be", "been", "'s", "'re") for w in words)
    if modal in ("will", "shall", "'ll"):
        return ("Future Perfect" if perfect else "Future Continuous" if cont else "Future Simple"), passive
    if modal:
        return f"Modal ({modal}) + V1", passive
    first = aux[0] if aux else root
    past = first.tag_ == "VBD" or first.lower_ in ("had", "was", "were", "did")
    if perfect:
        return ("Past Perfect" if past else "Present Perfect") + (" Continuous" if cont else ""), passive
    if cont:
        return ("Past" if past else "Present") + " Continuous", passive
    if passive:
        return ("Past Simple" if past else "Present Simple"), passive
    if root.tag_ == "VBD" or (aux and aux[0].lower_ == "did"):
        return "Past Simple", passive
    if root.tag_ in ("VBZ", "VBP") or (aux and aux[0].lower_ in ("do", "does")):
        return "Present Simple", passive
    return None, passive


def clause_role_of(tok, roles):
    return roles.get(tok.i, "")


# ---------------------------------------------------------------- why this part of speech
def forms(word):
    w = re.escape(word.lower())
    stem = w[:-1] if w.endswith("e") else w[:-1] + "i" if w.endswith("y") else w
    last = w[-1:]
    return re.compile(r"^(" + "|".join([w, w + "s", w + "es", w + "d", w + "ed", w + "ing", stem + "ing", stem + "ed",
                                        stem + "es", w + last + "ed", w + last + "ing"]) + r")$")


def find_target(doc, word):
    parts = word.lower().split()
    if len(parts) > 1:  # multi-word item like "prior to": use its first token
        for t in doc:
            if t.lower_ == parts[0] and all(doc[t.i + k].lower_ == p for k, p in enumerate(parts) if t.i + k < len(doc)):
                return t
        return None
    rx = forms(word)
    return next((t for t in doc if rx.match(t.lower_)), None)


def q(t):
    return f"“{t.text}”"


def where(head, roles):
    r = roles.get(head.i, "")
    if head.dep_ == "pobj":
        prep = head.head
        lead = prep.head.text + " " + prep.text if prep.head.dep_ == "prep" or (prep.i > 0 and prep.doc[prep.i - 1].i == prep.head.i and prep.head.pos_ == "ADJ") else prep.text
        return f" ในวลีบุพบท “{lead} ...”"
    return f" ซึ่งเป็น{ROLE_TH[r]} ({r})" if r in ("S", "O", "C") else ""


def subject_of(verb):
    while verb is not None:
        s = next((c for c in verb.children if c.dep_ in S_DEPS), None)
        if s is not None:
            return s
        if verb.dep_ in ("conj", "xcomp") and verb.head is not verb:
            verb = verb.head
        else:
            return None
    return None


def reason(t, roles, pos):
    d, h = t.dep_, t.head
    if pos == "n" or pos == "pron":
        if d in ("nsubj", "nsubjpass"):
            v = h
            return f"เป็นประธาน (S) ของกริยา {q(v)} ประธานต้องเป็นคำนามหรือสรรพนาม"
        if d in ("dobj", "iobj", "dative", "obj"):
            return f"เป็นกรรม (O) ที่ตามหลังกริยา {q(h)} กรรมต้องเป็นคำนามหรือสรรพนาม"
        if d == "pobj":
            return f"ตามหลังบุพบท {q(h)} บุพบทต้องตามด้วยคำนาม"
        if d == "attr":
            return f"ตามหลัง {q(h)} เป็นส่วนเติมเต็ม (C) บอกว่าประธานคืออะไร"
        if d == "compound":
            return f"อยู่หน้าคำนาม {q(h)} ทำหน้าที่ขยายแบบคำนามประสม (noun + noun)"
        if d == "poss":
            return f"อยู่หน้าคำนาม {q(h)} บอกความเป็นเจ้าของ"
        if d == "appos":
            return f"อธิบายเพิ่มเติมคำนาม {q(h)} ที่อยู่ข้างหน้า"
        if d == "npadvmod":
            return "เป็นคำนามบอกเวลา/ปริมาณที่ทำหน้าที่ขยายกริยา"
        if d == "conj":
            return f"เชื่อมด้วย and/or กับคำนาม {q(h)} จึงต้องเป็นคำนามเหมือนกัน"
        if d == "ROOT" or d in ("nsubj",):
            return None
    if pos == "adj":
        if d in ("amod", "nummod", "det") or (d in ("compound",) and t.pos_ == "ADJ"):
            return f"อยู่หน้าคำนาม {q(h)} เพื่อขยายนาม{where(h, roles)}"
        if d in ("acomp", "oprd") or (d == "xcomp" and t.pos_ == "ADJ"):
            s = subject_of(h)
            obj = next((c for c in h.children if c.dep_ == "dobj"), None)
            if obj is not None and d in ("oprd", "xcomp"):
                return f"ตามหลังกรรม {q(obj)} บอกสภาพของกรรม (keep/make + O + adj)"
            subj = f" บอกลักษณะของประธาน {q(s)}" if s is not None else " บอกลักษณะของประธาน"
            return f"ตามหลังกริยา {q(h)} (linking verb){subj}"
        if d == "attr":
            return f"ตามหลัง {q(h)} บอกลักษณะของประธาน"
        if d == "conj":
            return f"เชื่อมด้วย and/or กับ {q(h)} จึงต้องเป็นคุณศัพท์เหมือนกัน"
        if d == "advmod" or d == "npadvmod":
            return None
        if d == "dep" or d == "ROOT":
            return None
    if pos == "v":
        modal = next((c for c in t.children if c.dep_ in ("aux", "auxpass") and c.tag_ == "MD"), None)
        to = next((c for c in t.children if c.dep_ == "aux" and c.lower_ == "to"), None)
        if t.dep_ == "ROOT" or t.dep_ in ("conj", "advcl", "relcl", "ccomp", "xcomp", "pcomp", "acl"):
            if to is not None:
                return f"ตามหลัง to (to-infinitive) ต่อจาก {q(h)} ต้องใช้กริยารูปฐาน"
            if modal is not None:
                return f"ตามหลัง modal verb {q(modal)} ต้องใช้กริยารูปฐาน (V1)"
            if any(c.dep_ == "auxpass" for c in t.children):
                return "อยู่หลัง be ในรูป passive (be + V3) เป็นกริยาหลักของประโยค"
            if any(c.dep_ == "aux" and c.lower_ in ("have", "has", "had") for c in t.children):
                return "อยู่หลัง have/has/had ในรูป perfect (have + V3)"
            if t.dep_ == "ROOT" and not any(c.dep_ in S_DEPS for c in t.children) and t.tag_ == "VB":
                return "ขึ้นต้นประโยคคำสั่ง/ขอร้อง (Please + V1) ใช้กริยารูปฐาน"
            s = subject_of(t)
            if s is not None:
                return f"เป็นกริยาแท้ (V) ของประธาน {q(s)}"
            if t.tag_ == "VBG" and d in ("pcomp",):
                return f"ตามหลังบุพบท {q(h)} กริยาต้องเติม -ing"
            return "เป็นกริยาหลักของประโยค"
        if d == "amod":
            return f"รูป V-ed/V-ing อยู่หน้าคำนาม {q(h)} ทำหน้าที่ขยายนาม"
        return None
    if pos == "adv":
        if d in ("advmod", "npadvmod"):
            if h.pos_ in ("VERB", "AUX"):
                return f"ขยายกริยา {q(h)} บอกว่าทำอย่างไร/เมื่อไหร่ ถ้าตัดออกประโยคก็ยังครบ"
            if h.pos_ == "ADJ":
                return f"อยู่หน้าคุณศัพท์ {q(h)} เพื่อขยายคุณศัพท์"
            if h.pos_ == "ADV":
                return f"ขยาย adverb {q(h)}"
            if h.pos_ in ("NUM",) or h.dep_ == "nummod" or any(c.pos_ == "NUM" for c in h.children):
                return "ขยายตัวเลข/จำนวน (ประมาณ, เกือบ)"
            return "ขยายทั้งประโยค ถ้าตัดออกประโยคก็ยังครบ"
        if d == "prt":
            return f"เป็นส่วนหนึ่งของกริยาวลี {q(h)} + {t.text}"
        return None
    if pos == "prep":
        obj = next((c for c in t.children if c.dep_ in ("pobj", "pcomp")), None)
        if d in ("prep", "agent", "dative") or obj is not None:
            tail = f"คำนาม {q(obj)}" if obj is not None else "คำนาม"
            return f"อยู่หน้า{tail} สร้างเป็นวลีบุพบท (ห้ามตามด้วยประโยค S + V)"
        return None
    if pos == "conj":
        if d == "mark":
            return f"นำหน้าประโยคย่อยที่มีกริยา {q(h)} เชื่อมกับประโยคหลัก (ตามด้วย S + V)"
        if d == "cc":
            return "เชื่อมคำหรือประโยคสองส่วนที่มีหน้าที่เท่ากัน"
        if d == "advmod" and h.pos_ in ("VERB", "AUX"):
            return f"นำหน้าประโยคย่อยที่มีกริยา {q(h)} เชื่อมกับประโยคหลัก"
        return None
    return None


def analyze(sentence, words):
    doc = nlp(sentence)
    root = next((t for t in doc if t.dep_ == "ROOT"), None)
    out = {}
    if root is not None and root.pos_ in ("VERB", "AUX"):
        roles = {}
        label_clause(root, roles)
        segs = []
        for t in doc:
            r = "" if t.dep_ == "punct" else roles.get(t.i, "M")
            if segs and segs[-1][1] == r:
                segs[-1][0] += t.text_with_ws
            elif segs and r == "" and t.text in ",.;:!?" and not t.whitespace_ == "" and False:
                segs[-1][0] += t.text_with_ws
            else:
                if segs and segs[-1][0].endswith(" ") and r:
                    pass
                segs.append([t.text_with_ws, r])
        # move trailing spaces out of labeled segments so underlines stop at the word
        clean = []
        for text, r in segs:
            core = text.rstrip(" ")
            clean.append([core, r])
            if len(core) < len(text):
                clean.append([" ", ""])
        tense, passive = tense_of(root)
        out = {"g": clean, "t": tense, "p": passive}
    else:
        roles = {}
    reasons = {}
    for w, cands in words.items():
        t = find_target(doc, w)
        if t is None:
            continue
        guess = "adj" if t.dep_ == "amod" else SPACY2POS.get(t.pos_)
        pos = guess if guess in cands else (cands[0] if len(cands) == 1 else None)
        if pos is None:
            continue
        r = reason(t, roles, pos)
        if r:
            reasons[w] = [pos, f"{r} → จึงเป็น {POS_EN[pos]} ({POS_TH[pos]})"]
    if reasons:
        out["r"] = reasons
    return out


if __name__ == "__main__":
    res = {}
    for i, (sentence, words) in enumerate(jobs.items()):
        a = analyze(sentence, words)
        if a:
            res[sentence] = a
    json.dump(res, open(os.path.join(ROOT, "data", "annotations.json"), "w", encoding="utf-8"),
              ensure_ascii=False, separators=(",", ":"))
    n_g = sum(1 for a in res.values() if "g" in a)
    n_r = sum(len(a.get("r", {})) for a in res.values())
    n_w = sum(len(w) for w in jobs.values())
    print(f"{len(jobs)} sentences: {n_g} with structure, reasons for {n_r}/{n_w} word uses -> data/annotations.json")
