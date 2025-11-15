import os
import threading
import uuid
from dataclasses import dataclass
from typing import List

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from core.category_data import CATEGORY_KEYWORDS, CATEGORY_PRIORITY, WEIGHT_PROFILES
from core.mistral_client import embed_text, embed_texts


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


COLLECTION_NAME = os.getenv("CATEGORY_COLLECTION", "category_profiles")
VECTOR_DIM = _int_env("CATEGORY_VECTOR_DIM", 1024)
EMBED_BATCH_SIZE = _int_env("CATEGORY_PROFILE_BATCH", 8)
SCORE_THRESHOLD = _float_env("CATEGORY_SCORE_THRESHOLD", 0.2)

_client: QdrantClient | None = None
_client_lock = threading.Lock()
_sync_lock = threading.Lock()
_profiles_synced = False


@dataclass
class CategoryProfile:
    name: str
    description: str
    payload: dict


def _human_name(name: str) -> str:
    return name.replace("_", " ").title()


def _keywords_sentence(name: str) -> str:
    keywords = CATEGORY_KEYWORDS.get(name, [])
    if not keywords:
        return ""
    words = [kw for kw, _ in keywords][:8]
    if not words:
        return ""
    return f"Common signals: {', '.join(words)}."


def _weight_sentence(name: str) -> str:
    weights = WEIGHT_PROFILES.get(name, WEIGHT_PROFILES["general"])
    ordered = sorted(weights.items(), key=lambda kv: kv[1], reverse=True)
    pieces = [f"{label.replace('_', ' ')} ({weight*100:.0f}%)" for label, weight in ordered]
    return "Focus areas: " + ", ".join(pieces)


def _build_profiles() -> List[CategoryProfile]:
    profiles: List[CategoryProfile] = []
    for name in CATEGORY_PRIORITY:
        readable = _human_name(name)
        description = (
            f"{readable} startups share similar go-to-market patterns. "
            f"{_keywords_sentence(name)} {_weight_sentence(name)}"
        ).strip()
        payload = {
            "category": name,
            "display_name": readable,
            "weights": WEIGHT_PROFILES.get(name, {}),
            "keywords": [kw for kw, _ in CATEGORY_KEYWORDS.get(name, [])],
        }
        profiles.append(CategoryProfile(name=name, description=description, payload=payload))
    return profiles


def _get_client() -> QdrantClient:
    global _client
    if _client is not None:
        return _client

    with _client_lock:
        if _client is None:
            url = os.getenv("QDRANT_URL", "http://localhost:6333")
            api_key = os.getenv("QDRANT_API_KEY")
            _client = QdrantClient(url=url, api_key=api_key)
    return _client


def _ensure_collection(client: QdrantClient) -> None:
    if client.collection_exists(COLLECTION_NAME):
        return
    client.create_collection(
        COLLECTION_NAME,
        vectors_config=qmodels.VectorParams(size=VECTOR_DIM, distance=qmodels.Distance.COSINE),
    )


def _upsert_profiles(client: QdrantClient, profiles: List[CategoryProfile]) -> None:
    texts = [profile.description for profile in profiles]
    vectors = embed_texts(texts, batch_size=EMBED_BATCH_SIZE)
    points = [
        qmodels.PointStruct(
            id=str(uuid.uuid5(uuid.NAMESPACE_DNS, profile.name)),
            vector=vectors[idx],
            payload=profile.payload,
        )
        for idx, profile in enumerate(profiles)
    ]
    client.upsert(collection_name=COLLECTION_NAME, wait=True, points=points)


def sync_category_profiles(force: bool = False) -> int:
    profiles = _build_profiles()
    global _profiles_synced
    with _sync_lock:
        if _profiles_synced and not force:
            return 0

        client = _get_client()
        _ensure_collection(client)

        needs_refresh = True
        if not force:
            try:
                count = client.count(collection_name=COLLECTION_NAME).count
                if count >= len(profiles):
                    needs_refresh = False
            except Exception:
                needs_refresh = True

        if needs_refresh:
            _upsert_profiles(client, profiles)
            written = len(profiles)
        else:
            written = 0

        _profiles_synced = True
        return written


def _score_to_similarity(score: float | None) -> float:
    if score is None:
        return 0.0
    return max(0.0, min(1.0, (score + 1) / 2))


def detect_category_vector(idea: str) -> str | None:
    if not idea:
        return None

    try:
        sync_category_profiles()
        client = _get_client()
        vector = embed_text(idea)
        if not vector:
            return None
        hits = client.search(
            collection_name=COLLECTION_NAME,
            query_vector=vector,
            limit=3,
            with_payload=True,
        )
    except Exception:
        return None

    best_category: str | None = None
    best_similarity = 0.0
    for hit in hits:
        payload = hit.payload or {}
        category = payload.get("category")
        similarity = _score_to_similarity(hit.score)
        if not category:
            continue
        if similarity > best_similarity:
            best_category = category
            best_similarity = similarity

    if best_category and best_similarity >= SCORE_THRESHOLD:
        return best_category
    return best_category


if __name__ == "__main__":
    count = sync_category_profiles(force=True)
    print(f"Pushed {count} categories into Qdrant collection '{COLLECTION_NAME}'.")
