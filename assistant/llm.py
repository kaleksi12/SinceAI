"""Thin client for any OpenAI-compatible chat API (we use Featherless.ai with open-weights models).

Settings come from .env (see .env.example): FEATHERLESS_API_KEY, FEATHERLESS_BASE_URL, LLM_MODEL.
Every reply is cached on disk, so repeating an identical request (same model and messages) costs nothing and
returns the same text. That keeps evaluation runs cheap and reproducible.
"""
import hashlib
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI  # only an HTTP client for the OpenAI-compatible protocol; no OpenAI service is used

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")  # real environment variables win over .env

CACHE_DIR = ROOT / ".llm_cache"  # git-ignored
# Model families that think before answering by default (Qwen3.5 and later); see complete().
NO_THINKING_PREFIXES = ("Qwen/Qwen3.5", "Qwen/Qwen3.6", "Qwen/Qwen3.8")
stats = {"calls": 0, "cache_hits": 0}  # printed in run summaries
_client = None


def _get_client():
    """Create the API client on first use (so importing this module never needs a key)."""
    global _client
    if _client is None:
        key = os.environ.get("FEATHERLESS_API_KEY")
        if not key:
            raise RuntimeError("FEATHERLESS_API_KEY is not set (copy .env.example to .env)")
        _client = OpenAI(api_key=key, base_url=os.environ.get("FEATHERLESS_BASE_URL", "https://api.featherless.ai/v1"),
                         max_retries=4, timeout=120)  # retries cover rate limits (Featherless limits concurrency)
    return _client


def complete(messages, model=None, temperature=0.0, max_tokens=1200):
    """Return the model's reply text. Identical requests are served from the cache."""
    model = model or os.environ.get("LLM_MODEL")  # the argument wins, then .env
    if not model:
        raise RuntimeError("LLM_MODEL is not set")
    # Reasoning models spend the whole token budget on hidden "thinking" and return an empty answer, so switch it off.
    extra = {"chat_template_kwargs": {"enable_thinking": False}} if model.startswith(NO_THINKING_PREFIXES) else None
    # The cache key is a hash of everything that changes the reply: model, settings and the full messages.
    # (`extra` is only added when set, so cached replies of other models keep their keys.)
    parts = [model, temperature, max_tokens, messages] + ([extra] if extra else [])
    key = hashlib.sha256(json.dumps(parts, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    path = CACHE_DIR / (key + ".json")
    if path.exists():
        stats["cache_hits"] += 1
        return json.loads(path.read_text(encoding="utf-8"))["text"]
    kwargs = {"extra_body": extra} if extra else {}
    resp = _get_client().chat.completions.create(model=model, messages=messages, temperature=temperature, max_tokens=max_tokens, **kwargs)  # temperature 0: repeatable
    text = resp.choices[0].message.content or ""
    stats["calls"] += 1
    if text:  # never cache an empty reply: it would be served again on every re-run
        CACHE_DIR.mkdir(exist_ok=True)
        path.write_text(json.dumps({"model": model, "text": text}, ensure_ascii=False), encoding="utf-8")
    return text


def list_models():
    """All model ids the configured key can use (used by scripts/smoke_llm.py)."""
    return sorted(m.id for m in _get_client().models.list())
