"""Rule-based scoring (no AI). Each score is 0-10."""
import re
HOOK_WORDS = r"slap|slaps|slapped|gasp|scream|shout|blood|dead|die|kill|poison|dagger|knife|sword|betray|lie|lied|liar|secret|truth|reveal|pregnan|child|baby|divorce|annul|marry|married|wedding|duke|prince|king|queen|crown|traitor|murder|confess|forgive|leave|get out|how dare|you'll regret|never|stop|drop|shatter|slam|grab|throw|collapse|faint|fire|arrest|guards|kneel|bow|beg"
HOOK_ACTION = r"slap|strike|strikes|shove|slam|shatter|drops|hurl|grabs|lunges|collapses|draws|stabs|gasps|tears|spits|throws|drags|kneel"
CLIFF_WORDS = r"who|what|why|how|where|you\?|impossible|no\b|can't be|it was you|you knew|i know|know who|the truth|your .* (is|was)|killed|alive|dead|name|brother|father|mother|child|baby|pregnan"
BAD_START = re.compile(r"^(and|but|so|then|that|which|because|also|or|yet|still|however)\b", re.I)

def clip_text(events):
    return " ".join(e["text"] for e in events if e["kind"] == "DIALOGUE")

def score_clip(ep, events, start, end, scene_starts):
    dur = end - start
    dlg = [e for e in events if e["kind"] == "DIALOGUE"]
    first3 = [e for e in events if e["start"] < start + 3.5 and e["end"] > start]
    last6 = [e for e in events if e["end"] > end - 6]
    # hook
    h = 2.0
    t3 = " ".join(e["text"] for e in first3 if e["kind"] in ("DIALOGUE", "ACTION")).lower()
    if re.search(HOOK_ACTION, t3): h += 3
    if re.search(HOOK_WORDS, t3): h += 2
    if "!" in t3 or "?" in t3: h += 1.5
    d3 = [e for e in first3 if e["kind"] == "DIALOGUE"]
    if d3 and len(d3[0]["text"]) < 90: h += 1  # short punchy opener
    # cliffhanger
    c = 1.5
    tail = " ".join(e["text"] for e in last6).lower()
    last_d = dlg[-1]["text"].strip() if dlg else ""
    if last_d.endswith("?"): c += 3
    if last_d.endswith(("...", "—", "-", "…")): c += 2.5
    if re.search(CLIFF_WORDS, tail): c += 1.5
    if any(e["kind"] == "SOUND FX" and re.search(r"stinger|sting|cliffhanger|ominous|swell|silence|gasp|heartbeat", e["text"], re.I) for e in last6): c += 2
    if end >= ep["duration"] - 1.5: c += 1.5          # episode ends are written as cliffhangers
    if events and events[-1]["kind"] == "DIALOGUE" and end - events[-1]["end"] < 1.0: c -= 0.5
    # makes sense alone
    s = 5.0
    if any(abs(start - ss) < 0.6 for ss in scene_starts): s += 2.5
    if ep["episode"] == 1 and start < 2: s += 1.5
    if dlg and BAD_START.match(dlg[0]["text"].strip().strip('"')): s -= 2.5
    if len(dlg) < 3: s -= 2
    names = len({e["speaker"] for e in dlg})
    if names > 4: s -= 1.5
    # intensity
    txt = clip_text(events).lower()
    i = min(10, 2 + len(re.findall(HOOK_WORDS, txt)) * 0.7 + txt.count("!") * 0.4 + len(dlg) / max(dur, 1) * 8)
    cl = lambda x: max(0.0, min(10.0, x))
    return dict(hook=cl(h), cliff=cl(c), standalone=cl(s), intensity=cl(i))

def candidates(ep, cfg):
    from config import MIN_LEN, MAX_LEN
    ev = [e for e in ep["events"] if e["end"] > e["start"] or e["kind"] != "CAMERA"]
    starts = sorted({e["start"] for e in ev if e["kind"] in ("DIALOGUE", "ACTION")} | {s["start"] for s in ep["scenes"]})
    ends = sorted({e["end"] for e in ev if e["kind"] == "DIALOGUE"} | {ep["duration"]})
    scene_starts = [s["start"] for s in ep["scenes"]]
    out = []
    for st in starts:
        for en in ends:
            d = en - st
            if d < MIN_LEN or d > MAX_LEN: continue
            inside = [e for e in ep["events"] if e["start"] >= st - 0.01 and e["end"] <= en + 0.5]
            out.append((st, en, inside))
    return out, scene_starts
