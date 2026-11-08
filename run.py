import sys, json, csv, os, glob
from parse import load_all
from score import score_clip, candidates, clip_text
import config as C

def fmt(t): return f"{int(t//60):02d}:{t%60:05.2f}"

def overlap(a, b):
    if a["episode"] != b["episode"]: return 0
    inter = min(a["end"], b["end"]) - max(a["start"], b["start"])
    return max(0, inter) / min(a["end"] - a["start"], b["end"] - b["start"])

def total(s): return C.W_HOOK*s["hook"] + C.W_CLIFF*s["cliff"] + C.W_STAND*s["standalone"] + C.W_INTENSITY*s["intensity"]

def pick(clips):
    chosen = []
    for c in sorted(clips, key=lambda x: -x["total"]):
        if sum(1 for k in chosen if k["episode"] == c["episode"]) >= C.MAX_PER_EPISODE: continue
        if any(overlap(c, k) > C.OVERLAP_LIMIT for k in chosen): continue
        chosen.append(c)
    return chosen

def validate(c, ep):
    probs = []
    d = c["end"] - c["start"]
    if not (C.MIN_LEN <= d <= C.MAX_LEN): probs.append("length")
    if c["end"] > ep["duration"] + 0.5: probs.append("beyond_episode")
    return probs

def main(folder, out):
    os.makedirs(out, exist_ok=True)
    eps = load_all(folder); allc = []
    for ep in eps:
        cands, ss = candidates(ep, C)
        for st, en, inside in cands:
            sc = score_clip(ep, inside, st, en, ss)
            allc.append(dict(episode=ep["episode"], start=st, end=en, **sc,
                             transcript=" | ".join(f'{e["speaker"]}: {e["text"]}' for e in inside if e["kind"] == "DIALOGUE")))
    for c in allc: c["total"] = total(c)
    best = pick(allc)
    byep = {e["episode"]: e for e in eps}
    for c in best:
        c["problems"] = ",".join(validate(c, byep[c["episode"]]))
        dl = [e for e in byep[c["episode"]]["events"] if e["kind"] == "DIALOGUE" and c["start"]-0.01 <= e["start"] and e["end"] <= c["end"]+0.5]
        first3 = [e for e in dl if e["start"] < c["start"] + 4]
        c["hook_line"] = (first3[0]["speaker"] + ": " + first3[0]["text"]) if first3 else ""
        c["cliff_line"] = (dl[-1]["speaker"] + ": " + dl[-1]["text"]) if dl else ""
        c["why"] = f"hook {c['hook']:.1f}, cliffhanger {c['cliff']:.1f}, standalone {c['standalone']:.1f} (rule-based)"
    best.sort(key=lambda x: -x["total"])
    for i, c in enumerate(best, 1): c["rank"] = i
    if C.API_KEY or C.PROVIDER == "file":
        from llm import rerank
        print("LLM re-ranking top", C.TOP_N_FOR_LLM, "with", "offline file scores" if C.PROVIDER == "file" else C.MODEL)
        if C.PROVIDER == "file":
            from llm import rerank_from_file
            top = rerank_from_file(best, f"{out}/claude_review_scores.json")
        else:
            top = rerank(best, byep, checkpoint_dir=out)
        ok = [c for c in top if "llm_total" in c]
        ok.sort(key=lambda x: -x["llm_total"])
        for i, c in enumerate(ok, 1):
            c["rank_llm"] = i; c["hook_line"] = c["llm"].get("hook_line", c["hook_line"])
            c["cliff_line"] = c["llm"].get("cliffhanger_line", c["cliff_line"]); c["why"] = c["llm"].get("why", c["why"])
        json.dump(ok, open(f"{out}/promos_llm.json", "w"), indent=1)
        with open(f"{out}/promos_llm.csv", "w", newline="") as f:
            w = csv.writer(f); w.writerow(["rank","rank_rule_based","episode","start","end","length_s","hook","cliffhanger","standalone","hook_line","cliffhanger_line","why"])
            for c in ok:
                j = c["llm"]; w.writerow([c["rank_llm"],c["rank"],c["episode"],fmt(c["start"]),fmt(c["end"]),round(c["end"]-c["start"],1),j["hook"],j["cliffhanger"],j["standalone"],c["hook_line"],c["cliff_line"],c["why"]])
        print("LLM ok:", len(ok), "failed:", len(top)-len(ok))
        errs = [c["llm_error"] for c in top if "llm_error" in c]
        if errs: print("First error:", errs[0])
    json.dump(best, open(f"{out}/promos_rule_based.json", "w"), indent=1)
    with open(f"{out}/promos_rule_based.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(["rank","episode","start","end","length_s","hook","cliff","standalone","total","hook_line","cliff_line","why","problems"])
        for c in best:
            w.writerow([c["rank"],c["episode"],fmt(c["start"]),fmt(c["end"]),round(c["end"]-c["start"],1),round(c["hook"],1),round(c["cliff"],1),round(c["standalone"],1),round(c["total"],2),c["hook_line"],c["cliff_line"],c["why"],c["problems"]])
    print("candidates:", len(allc), "selected:", len(best))
    for c in best[:12]:
        print(f'#{c["rank"]} ep{c["episode"]} {fmt(c["start"])}-{fmt(c["end"])} {c["total"]:.2f} | {c["hook_line"][:60]} || {c["cliff_line"][:60]}')

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "outputs")
