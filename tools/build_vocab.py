#!/usr/bin/env python3
"""สร้าง vocab-data.js — รวมคำศัพท์ HSK 1-5 (มีคำแปลไทย) กับคำศัพท์ทั่วไปจาก CC-CEDICT

แหล่งข้อมูล
  - index.html            : คำศัพท์ HSK 1-5 พร้อมคำแปลไทย (ของโปรเจกต์นี้)
  - cedict_ts.u8          : CC-CEDICT (CC BY-SA 4.0, https://www.mdbg.net/chinese/dictionary?page=cc-cedict)
                            ใช้จากแพ็กเกจ npm `hanzi` (lib/data/cedict_ts.u8.js)
  - SUBTLEX-CH-WF         : ความถี่คำจากซับไตเติล (Cai & Brysbaert 2010) — ใช้จัดลำดับความถี่เท่านั้น
                            (แพ็กเกจ npm `hanzi`, lib/data/SUBTLEX-CH-WF, เข้ารหัส GBK)
  - jieba dict.txt        : ความถี่คำจากพจนานุกรม jieba (PyPI `jieba`) — ใช้เสริมการจัดลำดับ

ใช้งาน:
  python3 tools/build_vocab.py <cedict_ts.u8.js> <SUBTLEX-CH-WF> <jieba dict.txt> [จำนวนคำเพิ่มเติม]
"""
import json, re, sys, math

cedict_path, subtlex_path, jieba_path = sys.argv[1:4]
EXTRA_LIMIT = int(sys.argv[4]) if len(sys.argv) > 4 else 40000

# ---------- HSK จาก index.html ----------
src = open("index.html", encoding="utf-8-sig").read()
hsk = re.findall(r'^\["([^"]+)","([^"]*)","([^"]*)",(\d),"([^"]*)"\],?\s*$', src, re.M)
hsk_words = {w for w, *_ in hsk}

# ---------- พินอิน: ตัวเลข -> วรรณยุกต์ ----------
TONES = {"a": "āáǎàa", "e": "ēéěèe", "i": "īíǐìi", "o": "ōóǒòo", "u": "ūúǔùu", "ü": "ǖǘǚǜü"}
def syl(s):
    m = re.fullmatch(r"([a-zü:]+)([1-5])", s, re.I)
    if not m:
        return s.replace("u:", "ü").replace("U:", "Ü")
    body, t = m.group(1).replace("u:", "ü").replace("U:", "Ü"), int(m.group(2))
    low = body.lower()
    if "a" in low: i = low.index("a")
    elif "e" in low: i = low.index("e")
    elif "ou" in low: i = low.index("o")
    else:
        idx = [k for k, c in enumerate(low) if c in "aeiouü"]
        if not idx: return body
        i = idx[-1]
    c = low[i]
    rep = TONES[c][t - 1]
    if body[i].isupper(): rep = rep.upper()
    return body[:i] + rep + body[i + 1:]
def pinyin(p):
    out = [syl(s) for s in p.split()]
    return "".join(out) if len(out) <= 4 else " ".join(out)

# ---------- CC-CEDICT ----------
BAD = re.compile(r"^(surname |variant of|old variant|archaic variant|Japanese variant|see [^\s]|used in |abbr\. for|erhua variant|\(old\)|\(archaic\)|\(Cantonese\)|\(Tw\)|\(Taiwan\)|\(dialect\)|\(literary\)|\(classical\))", re.I)
ced = {}
for line in open(cedict_path, encoding="utf-8"):
    m = re.match(r"^(\S+) (\S+) \[([^\]]+)\] /(.+)/\s*$", line)
    if not m: continue
    trad, simp, py, defs = m.groups()
    if not re.fullmatch(r"[㐀-鿿]+", simp): continue
    if py[:1].isupper() and simp not in hsk_words:  # ชื่อเฉพาะ
        continue
    ds = [d.strip() for d in defs.split("/") if d.strip() and not d.startswith("CL:")]
    good = [d for d in ds if not BAD.match(d)]
    if not good: continue
    en = []
    for d in good:
        d = re.sub(r"\s*\[[^\]]*\]", "", d)                     # ตัดพินอินในวงเล็บ
        d = re.sub(r"([㐀-鿿]+)\|([㐀-鿿]+)", r"\2", d)  # ตัวเต็ม|ตัวย่อ -> ตัวย่อ
        if re.match(r"(also pr\.|also written|also called|pr\. |variant)", d, re.I): continue
        if d and d not in en: en.append(d)
    gloss = ""
    for d in en:
        nxt = (gloss + "; " + d) if gloss else d
        if len(nxt) > 70 and gloss: break
        gloss = nxt
    if len(gloss) > 90: gloss = gloss[:88].rstrip() + "…"
    prev = ced.get(simp)
    # เลือกรายการที่ไม่ใช่เสียงเบา/ตัวพิมพ์ใหญ่ และมีความหมายยาวกว่า
    score = (py[:1].islower(), len(good))
    if prev is None or score > prev[2]:
        ced[simp] = (pinyin(py), gloss, score)

# ---------- ความถี่ ----------
freq = {}
raw = open(subtlex_path, "rb").read().decode("gb18030", errors="ignore")
for line in raw.splitlines()[3:]:
    parts = line.split("\t")
    if len(parts) > 2:
        try: freq[parts[0]] = float(parts[2])  # ต่อ 1 ล้านคำ
        except ValueError: pass
jfreq = {}
for line in open(jieba_path, encoding="utf-8"):
    parts = line.split()
    if len(parts) >= 2: jfreq[parts[0]] = int(parts[1])
jtotal = sum(jfreq.values())
def score(w):
    s = freq.get(w, 0.0)
    j = jfreq.get(w, 0) / jtotal * 1e6
    return max(s, j * 0.6)

# ---------- รวม ----------
out = []
for w, p, th, lv, pos in hsk:
    en = ced.get(w, ("", "", None))[1]
    out.append([w, p, th, int(lv), pos, en])

extra = [(w, v) for w, v in ced.items() if w not in hsk_words and score(w) > 0]
extra.sort(key=lambda x: -score(x[0]))
extra = extra[:EXTRA_LIMIT]
n = len(extra)
b1, b2 = int(n * 0.2), int(n * 0.5)
for i, (w, (p, en, _)) in enumerate(extra):
    lv = 6 if i < b1 else 7 if i < b2 else 8   # 6 = พบบ่อย, 7 = ทั่วไป, 8 = ขั้นสูง
    out.append([w, p, "", lv, "", en])

with open("vocab-data.js", "w", encoding="utf-8") as f:
    f.write("// สร้างโดย tools/build_vocab.py — [จีน, พินอิน, ไทย, ระดับ, ชนิดคำ, อังกฤษ]\n")
    f.write("// ระดับ 1-5 = HSK (คำแปลไทยของโปรเจกต์), 6 = คำพบบ่อย, 7 = คำทั่วไป, 8 = คำขั้นสูง\n")
    f.write("// ความหมายภาษาอังกฤษจาก CC-CEDICT (CC BY-SA 4.0, MDBG)\n")
    f.write("window.VOCAB=[\n")
    f.write(",\n".join(json.dumps(r, ensure_ascii=False, separators=(",", ":")) for r in out))
    f.write("\n];\n")
print("HSK", len(hsk), "extra", n, "total", len(out), "bands", b1, b2 - b1, n - b2)
