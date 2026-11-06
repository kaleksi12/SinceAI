"""Thin OpenAI-compatible client with an on-disk response cache."""
import hashlib
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

CACHE_DIR = ROOT / ".llm_cache"
stats = {"calls": 0, "cache_hits": 0}
_client = None


def _get_client():
    global _client
    if _client is None:
        key = os.environ.get("FEATHERLESS_API_KEY")
        if not key:
            raise RuntimeError("FEATHERLESS_API_KEY is not set (copy .env.example to .env)")
        _client = OpenAI(api_key=key, base_url=os.environ.get("FEATHERLESS_BASE_URL", "https://api.featherless.ai/v1"),
                         max_retries=4, timeout=120)
    return _client


def complete(messages, model=None, temperature=0.0, max_tokens=1200):
    """Return the model's reply text. Identical requests are served from the cache."""
    model = model or os.environ.get("LLM_MODEL")
    if not model:
        raise RuntimeError("LLM_MODEL is not set")
    key = hashlib.sha256(json.dumps([model, temperature, max_tokens, messages], sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    path = CACHE_DIR / (key + ".json")
    if path.exists():
        stats["cache_hits"] += 1
        return json.loads(path.read_text(encoding="utf-8"))["text"]
    resp = _get_client().chat.completions.create(model=model, messages=messages, temperature=temperature, max_tokens=max_tokens)
    text = resp.choices[0].message.content or ""
    stats["calls"] += 1
    CACHE_DIR.mkdir(exist_ok=True)
    path.write_text(json.dumps({"model": model, "text": text}, ensure_ascii=False), encoding="utf-8")
    return text


def list_models():
    return sorted(m.id for m in _get_client().models.list())
