import hashlib
import math
import os
import random
import threading
import time
from typing import List

from dotenv import load_dotenv
from mistralai import Mistral
from mistralai.models import sdkerror

from core.prompts import SYSTEM_PROMPT

load_dotenv()


def _int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    try:
        return int(value) if value else default
    except (TypeError, ValueError):
        return default


def _float_env(name: str, default: float) -> float:
    value = os.getenv(name)
    try:
        return float(value) if value else default
    except (TypeError, ValueError):
        return default


def _bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


_CHAT_MODEL = os.getenv("MISTRAL_CHAT_MODEL", "mistral-large-latest")
_EMBED_MODEL = os.getenv("MISTRAL_EMBED_MODEL", "mistral-embed")
_EMBED_DIM = _int_env("MISTRAL_EMBED_DIM", 1024)
_EMBED_RETRY_LIMIT = _int_env("MISTRAL_EMBED_MAX_RETRIES", 3)
_EMBED_RETRY_DELAY = _float_env("MISTRAL_EMBED_RETRY_SECONDS", 2.0)
_EMBED_RPS_LIMIT = _float_env("MISTRAL_EMBED_RPS", 1.0)
_USE_FAKE_EMBEDDINGS = _bool_env("MOCK_MISTRAL_EMBEDDINGS", False)

_rate_lock = threading.Lock()
_last_rate_call = 0.0

client = Mistral(api_key=os.getenv("MISTRAL_API_KEY"))


def chat(prompt: str) -> str:
    """
    Send a single-turn prompt to Mistral and return the output text.
    """
    response = client.chat.complete(
        model=_CHAT_MODEL,
        response_format={"type": "json_object"},
        temperature=0.3,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
    )
    return response.choices[0].message.content.strip()


def _respect_rate_limit():
    if _EMBED_RPS_LIMIT <= 0:
        return
    minimum_interval = 1.0 / max(_EMBED_RPS_LIMIT, 1e-6)
    with _rate_lock:
        global _last_rate_call
        now = time.monotonic()
        wait_seconds = (_last_rate_call + minimum_interval) - now
        if wait_seconds > 0:
            time.sleep(wait_seconds)
            now = time.monotonic()
        _last_rate_call = now


def _call_embeddings(batch: List[str]):
    last_error: Exception | None = None
    for attempt in range(_EMBED_RETRY_LIMIT + 1):
        try:
            _respect_rate_limit()
            return client.embeddings.create(model=_EMBED_MODEL, inputs=batch)
        except sdkerror.SDKError as err:
            last_error = err
            message = str(err).lower()
            should_retry = "status 429" in message or "capacity" in message
            if attempt >= _EMBED_RETRY_LIMIT or not should_retry:
                raise
            sleep_seconds = _EMBED_RETRY_DELAY * (attempt + 1)
            time.sleep(max(0, sleep_seconds))
    if last_error:
        raise last_error


def embed_texts(texts: List[str], batch_size: int = 12) -> List[List[float]]:
    """
    Batch helper around the embeddings endpoint with basic throttling on 429s.
    """
    if not texts:
        return []

    if _USE_FAKE_EMBEDDINGS:
        return [_fake_embedding(text) for text in texts]

    chunk_size = max(1, batch_size)
    vectors: List[List[float]] = []
    index = 0
    while index < len(texts):
        batch = texts[index : index + chunk_size]
        try:
            resp = _call_embeddings(batch)
        except sdkerror.SDKError as err:
            message = str(err).lower()
            if "status 429" in message and chunk_size > 1:
                chunk_size = max(1, chunk_size // 2)
                continue
            raise
        vectors.extend([(item.embedding or []) for item in resp.data])
        index += len(batch)

    return vectors


def embed_text(text: str) -> List[float]:
    """
    Convenience wrapper for a single text.
    """
    embeddings = embed_texts([text], batch_size=1)
    return embeddings[0] if embeddings else []


def _fake_embedding(text: str) -> List[float]:
    """
    Deterministic local embedding for testing without calling Mistral.
    """
    seed_bytes = hashlib.sha256(text.encode("utf-8")).digest()
    seed = int.from_bytes(seed_bytes[:4], "big")
    rng = random.Random(seed)
    vec = [rng.uniform(-1.0, 1.0) for _ in range(_EMBED_DIM)]
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]
