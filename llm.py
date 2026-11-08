"""Batched LLM re-ranking with retries, progress, and resumable partial results."""
import json
import urllib.request
import urllib.error
import urllib.parse
import re
import time
import socket
from pathlib import Path
import config as C

SYSTEM_PROMPT = """You are an editor evaluating promo clips for a vertical microdrama app.
A good promo is 20-60 seconds, opens with a compelling hook, ends on an unresolved cliffhanger,
and makes sense to a viewer who has never seen the show.
For EACH clip, score hook, cliffhanger, and standalone clarity from 1 to 10.
Return one JSON object with this exact shape:
{"results":[{"index":1,"hook":1,"cliffhanger":1,"standalone":1,"hook_line":"...","cliffhanger_line":"...","why":"one concise sentence","better_start":null,"better_end":null}]}
Include exactly one result for every input index. Return JSON only."""

RETRYABLE_HTTP = {408, 429, 500, 502, 503, 504}

def _post(url, headers, body):
    req = urllib.request.Request(url, json.dumps(body).encode("utf-8"),
                                 {"Content-Type": "application/json", **headers})
    for attempt in range(1, C.LLM_MAX_ATTEMPTS + 1):
        try:
            with urllib.request.urlopen(req, timeout=C.LLM_TIMEOUT_SECONDS) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="ignore")[:600]
            if exc.code not in RETRYABLE_HTTP or attempt == C.LLM_MAX_ATTEMPTS:
                raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc
            delay = min(30, 5 * (2 ** (attempt - 1)))
            print(f"  HTTP {exc.code}; retry {attempt + 1}/{C.LLM_MAX_ATTEMPTS} in {delay}s", flush=True)
            time.sleep(delay)
        except (TimeoutError, socket.timeout, urllib.error.URLError) as exc:
            if attempt == C.LLM_MAX_ATTEMPTS:
                raise RuntimeError(f"Network timeout/connection error after {C.LLM_MAX_ATTEMPTS} attempts: {exc}") from exc
            delay = min(30, 5 * (2 ** (attempt - 1)))
            print(f"  Network timeout; retry {attempt + 1}/{C.LLM_MAX_ATTEMPTS} in {delay}s", flush=True)
            time.sleep(delay)

def call_llm(prompt):
    if C.PROVIDER == "gemini":
        model = urllib.parse.quote(C.MODEL, safe="-_.")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={C.API_KEY}"
        response = _post(url, {}, {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0, "responseMimeType": "application/json"}
        })
        return response["candidates"][0]["content"]["parts"][0]["text"]
    if C.PROVIDER == "anthropic":
        response = _post("https://api.anthropic.com/v1/messages",
                         {"x-api-key": C.API_KEY, "anthropic-version": "2023-06-01"},
                         {"model": C.MODEL, "max_tokens": 3000,
                          "messages": [{"role": "user", "content": prompt}]})
        return response["content"][0]["text"]
    response = _post(C.BASE_URL.rstrip("/") + "/chat/completions",
                     {"Authorization": f"Bearer {C.API_KEY}"},
                     {"model": C.MODEL, "temperature": 0,
                      "messages": [{"role": "user", "content": prompt}]})
    return response["choices"][0]["message"]["content"]

def _parse_json(text):
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        raise ValueError("Model response did not contain a JSON object")
    return json.loads(match.group(0))

def _clip_payload(index, clip, episode):
    events = [
        f'[{event["start"]:.1f}-{event["end"]:.1f}] {event["speaker"] or event["kind"]}: {event["text"][:160]}'
        for event in episode["events"]
        if event["kind"] in ("DIALOGUE", "ACTION", "SOUND FX")
        and event["start"] >= clip["start"] - 0.1
        and event["end"] <= clip["end"] + 0.5
    ]
    return {
        "index": index,
        "episode": clip["episode"],
        "logline": episode["logline"],
        "start_seconds": round(clip["start"], 2),
        "end_seconds": round(clip["end"], 2),
        "transcript": events
    }

def rerank(clips, eps_by_num, checkpoint_dir="outputs"):
    selected = clips[:C.TOP_N_FOR_LLM]
    batch_size = max(1, C.LLM_BATCH_SIZE)
    successful = {}
    checkpoint = Path(checkpoint_dir) / "promos_llm_partial.json"
    checkpoint.parent.mkdir(parents=True, exist_ok=True)

    # Resume: reuse clips already scored in an earlier run (matched by episode + start time).
    cached = {}
    if checkpoint.exists():
        try:
            cached = {(d["episode"], round(d["start"], 1)): d
                      for d in json.loads(checkpoint.read_text(encoding="utf-8")) if "llm" in d}
        except Exception:
            cached = {}

    batches = [selected[i:i + batch_size] for i in range(0, len(selected), batch_size)]
    for batch_no, batch in enumerate(batches, 1):
        first_index = (batch_no - 1) * batch_size + 1
        last_index = first_index + len(batch) - 1
        keys = [(c["episode"], round(c["start"], 1)) for c in batch]
        if all(k in cached for k in keys):
            for offset, (clip, k) in enumerate(zip(batch, keys)):
                clip["llm"], clip["llm_total"] = cached[k]["llm"], cached[k]["llm_total"]
                successful[first_index + offset] = clip
            print(f"LLM batch {batch_no}/{len(batches)} (clips {first_index}-{last_index}) reused from earlier run", flush=True)
            continue
        print(f"LLM batch {batch_no}/{len(batches)} (clips {first_index}-{last_index})", flush=True)
        payload = [_clip_payload(first_index + offset, clip, eps_by_num[clip["episode"]])
                   for offset, clip in enumerate(batch)]
        prompt = SYSTEM_PROMPT + "\n\nEvaluate these clips:\n" + json.dumps(payload, ensure_ascii=False)
        try:
            parsed = _parse_json(call_llm(prompt))
            results = parsed.get("results", [])
            by_index = {int(item["index"]): item for item in results}
            for offset, clip in enumerate(batch):
                idx = first_index + offset
                if idx not in by_index:
                    clip["llm_error"] = "Batch response omitted this clip"
                    continue
                result = by_index[idx]
                clip["llm"] = result
                clip["llm_total"] = (0.4 * float(result["hook"])
                                     + 0.4 * float(result["cliffhanger"])
                                     + 0.2 * float(result["standalone"]))
                successful[idx] = clip
        except Exception as exc:
            message = str(exc)[:500]
            print(f"  Batch {batch_no} failed: {message}", flush=True)
            for clip in batch:
                clip["llm_error"] = message

        # Persist completed successes after every batch, so a later failure doesn't erase them.
        checkpoint.write_text(json.dumps(list(successful.values()), indent=2), encoding="utf-8")
        print(f"  Completed: {len(successful)}/{len(selected)} clips", flush=True)

    return [clip for clip in selected if "llm" in clip]


def rerank_from_file(clips, path="outputs/claude_review_scores.json"):
    """Offline provider: scores written by a human/Claude review, matched by episode + start time."""
    data = {(d["episode"], round(d["start"], 1)): d for d in json.load(open(path, encoding="utf-8"))}
    out = []
    for clip in clips:
        d = data.get((clip["episode"], round(clip["start"], 1)))
        if not d: continue
        clip["llm"] = d
        clip["llm_total"] = 0.4*d["hook"] + 0.4*d["cliffhanger"] + 0.2*d["standalone"]
        out.append(clip)
    return out
