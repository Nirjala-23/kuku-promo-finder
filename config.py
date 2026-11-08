"""Settings. API key is read from the environment; never hardcode it here."""
import os
PROVIDER = os.getenv("PROMO_PROVIDER", "gemini")
MODEL = os.getenv("PROMO_MODEL", "gemini-3.8-flash")
API_KEY = os.getenv("PROMO_API_KEY", "")
BASE_URL = os.getenv("PROMO_BASE_URL", "")
MIN_LEN, MAX_LEN = 20.0, 60.0
TOP_N_FOR_LLM = 60
LLM_BATCH_SIZE = 5
LLM_MAX_ATTEMPTS = 3
LLM_TIMEOUT_SECONDS = 90
MAX_PER_EPISODE = 2
OVERLAP_LIMIT = 0.3
W_HOOK, W_CLIFF, W_STAND, W_INTENSITY = 0.35, 0.35, 0.15, 0.15
