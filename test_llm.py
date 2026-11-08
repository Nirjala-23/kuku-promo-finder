"""Quick connection check. Run: python3 test_llm.py"""
import config as C
from llm import call_llm
print("Provider:", C.PROVIDER, "| Model:", C.MODEL, "| key set:", bool(C.API_KEY), flush=True)
try:
    print("Reply:", call_llm('Reply with JSON only: {"ok": true}'), flush=True)
except Exception as exc:
    print("ERROR:", exc, flush=True)
