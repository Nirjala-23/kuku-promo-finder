# Promo Finder (Kuku assignment, Problem 1)
Finds 20-60s promo clips (hook + cliffhanger + makes sense alone) in microdrama screenplays.

## Run
    python3 run.py "<folder with episode-*.txt>" outputs
Works with no API key (rule-based scorer). Output: outputs/promos_rule_based.csv/.json

## Windows (PowerShell)
    $env:PROMO_PROVIDER="gemini"; $env:PROMO_MODEL="gemini-3.8-flash"; $env:PROMO_API_KEY="YOUR_KEY"
    python run.py data outputs
Offline demo (no key, uses saved review scores): `$env:PROMO_PROVIDER="file"`. Those scores only exist for the 30 clips reviewed; a new input needs a live model or the rule-based output.

## Swap the model (LLM re-rank)
    export PROMO_API_KEY=...  PROMO_PROVIDER=gemini  PROMO_MODEL=gemini-3.8-flash
Providers: gemini, anthropic, openai_compat, file (offline scores from outputs/claude_review_scores.json) (set PROMO_BASE_URL). Settings live in config.py.

## Steps
1 parse.py: screenplay -> events with timestamps (code)
2 score.py: ~14k candidate windows, 20-60s, start/end snapped to line boundaries; rule-based hook/cliffhanger/standalone scores (code)
3 run.py: rank, remove overlaps, max 2 per episode, validate length/timestamps (code)
4 llm.py: LLM re-scores only the top 60 clips (cheap at scale)

## Data
Scripts are Kuku's confidential content. They are NOT in this repo (.gitignore).

## Results
Final results were produced with gemini-3.6-flash on the free tier (60 of 60 top clips scored). Raw outputs are shared separately because they contain confidential script text. Input data is not included.
