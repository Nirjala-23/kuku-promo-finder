"""Parse Kuku microdrama screenplay .txt files into structured events."""
import re, glob, os, json

TS = r"(\d+):(\d+\.\d+)"
BLOCK = re.compile(r"\*\*(.+?):\*\*\s*\nStart: \(" + TS + r"\) \| End: \(" + TS + r"\)\s*\n(.*?)(?=\n\*\*[^*\n]+:\*\*\s*\nStart:|\nSCENE \d+|\n--- SCRIPT END|\Z)", re.S)
SCENE = re.compile(r"SCENE (\d+)\s*\nScene heading: (.*?)\nScene start: " + TS + r"\nScene end: " + TS)
NONSPEAK = {"CAMERA", "ACTION", "SOUND FX", "SFX", "MUSIC", "TEXT", "TITLE"}

def sec(m, s): return int(m) * 60 + float(s)

def parse_episode(path):
    t = open(path, encoding="utf-8").read()
    ep = int(re.search(r"EPISODE NUMBER: Episode (\d+)", t).group(1))
    logline = (re.search(r"EPISODE LOGLINE: (.*)", t) or [None, ""])[1]
    scenes = []
    for m in SCENE.finditer(t):
        scenes.append(dict(n=int(m.group(1)), heading=m.group(2).strip(),
                           start=sec(m.group(3), m.group(4)), end=sec(m.group(5), m.group(6))))
    events = []
    for m in BLOCK.finditer(t):
        label = m.group(1)
        name = re.sub(r"\s*\(.*?\)\s*$", "", label).strip().rstrip(" :").strip()
        tone = (re.search(r"\((.*?)\)\s*$", label) or [None, ""])[1]
        kind = name.upper() if name.upper() in NONSPEAK else "DIALOGUE"
        events.append(dict(kind=kind, speaker=name if kind == "DIALOGUE" else "", tone=tone,
                           start=sec(m.group(2), m.group(3)), end=sec(m.group(4), m.group(5)),
                           text=m.group(6).strip()))
    events.sort(key=lambda e: (e["start"], e["end"]))
    return dict(episode=ep, logline=logline, scenes=scenes, events=events,
                duration=max([s["end"] for s in scenes] or [0]))

def load_all(folder):
    files = sorted(glob.glob(os.path.join(folder, "episode-*.txt")))
    return [parse_episode(f) for f in files]

if __name__ == "__main__":
    import sys
    eps = load_all(sys.argv[1])
    for e in eps[:3] + eps[-2:]:
        d = sum(1 for x in e["events"] if x["kind"] == "DIALOGUE")
        print(e["episode"], "dur", e["duration"], "scenes", len(e["scenes"]), "events", len(e["events"]), "dialogue", d)
    print("episodes:", len(eps), "avg dur:", sum(e["duration"] for e in eps) / len(eps))
