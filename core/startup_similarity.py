import csv
import hashlib
import os
import threading
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import List

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from core.mistral_client import embed_text, embed_texts
from models import SimilarItem

DATASET_PATH = Path(os.getenv("STARTUP_DATASET_PATH", "unicorns till sep 2022.csv"))
COLLECTION_NAME = os.getenv("QDRANT_COLLECTION", "startup_pitches")


def _int_env(var: str, default: int) -> int:
    value = os.getenv(var)
    try:
        return int(value) if value else default
    except (TypeError, ValueError):
        return default


VECTOR_DIM = _int_env("QDRANT_VECTOR_DIM", 1024)
EMBED_BATCH_SIZE = _int_env("EMBED_BATCH_SIZE", 32)

_client: QdrantClient | None = None
_client_lock = threading.Lock()
_ingest_lock = threading.Lock()
_dataset_synced = False


@dataclass
class StartupRecord:
    point_id: str
    pitch: str
    payload: dict


def _clean(value: str | None) -> str:
    if value is None:
        return ""
    return value.replace("\u00a0", " ").strip()


def _get(row: dict, *keys: str) -> str:
    for key in keys:
        if key in row and row[key]:
            return _clean(row[key])
    return ""


def _parse_valuation(raw: str) -> float | None:
    raw = _clean(raw)
    if not raw:
        return None
    cleaned = (
        raw.replace("$", "")
        .replace("B", "")
        .replace("b", "")
        .replace(",", "")
        .strip()
    )
    try:
        return float(cleaned)
    except ValueError:
        return None


def _make_point_id(company: str, country: str, joined: str) -> str:
    base = f"{company}-{country}-{joined}".lower()
    return hashlib.md5(base.encode("utf-8")).hexdigest()


def _build_pitch(company: str, industry: str, country: str, city: str, joined: str, valuation: float | None, investors: str) -> str:
    parts: List[str] = []
    location = ", ".join(filter(None, [city, country]))

    descriptor = f"{company} operates in the {industry} space"
    if location:
        descriptor += f" out of {location}"
    parts.append(descriptor + ".")

    if joined:
        parts.append(f"It reached unicorn status on {joined}.")
    if valuation:
        parts.append(f"Latest reported valuation: ${valuation:.1f}B.")
    if investors:
        parts.append(f"Backed by {investors}.")

    return " ".join(parts)


@lru_cache(maxsize=1)
def _dataset_records() -> List[StartupRecord]:
    if not DATASET_PATH.exists():
        return []

    records: List[StartupRecord] = []
    with DATASET_PATH.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            normalized_row = {
                (k or "").replace("\u00a0", " ").strip(): v for k, v in row.items()
            }
            company = _get(normalized_row, "Company")
            if not company:
                continue
            industry = _get(normalized_row, "Industry") or "technology"
            country = _get(normalized_row, "Country")
            city = _get(normalized_row, "City")
            joined = _get(normalized_row, "Date Joined")
            investors = _get(normalized_row, "Investors")
            valuation = _parse_valuation(_get(normalized_row, "Valuation ($B)"))

            pitch = _build_pitch(
                company=company,
                industry=industry,
                country=country,
                city=city,
                joined=joined,
                valuation=valuation,
                investors=investors,
            )

            payload = {
                "company": company,
                "industry": industry,
                "country": country,
                "city": city,
                "date_joined": joined,
                "investors": investors,
                "valuation_billion": valuation,
                "status": "unicorn",
                "pitch": pitch,
            }

            records.append(
                StartupRecord(
                    point_id=_make_point_id(company, country, joined),
                    pitch=pitch,
                    payload=payload,
                )
            )
    return records


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
        vectors_config=qmodels.VectorParams(
            size=VECTOR_DIM, distance=qmodels.Distance.COSINE
        ),
    )


def _upsert_records(client: QdrantClient, records: List[StartupRecord]) -> None:
    texts = [record.pitch for record in records]
    vectors = embed_texts(texts, batch_size=EMBED_BATCH_SIZE)
    points = [
        qmodels.PointStruct(
            id=record.point_id,
            vector=vectors[idx],
            payload=record.payload,
        )
        for idx, record in enumerate(records)
    ]
    client.upsert(collection_name=COLLECTION_NAME, wait=True, points=points)


def sync_dataset(force: bool = False) -> int:
    """
    Pushes the CSV dataset into Qdrant. Returns the amount of points written.
    """
    records = _dataset_records()
    if not records:
        return 0

    global _dataset_synced

    with _ingest_lock:
        if _dataset_synced and not force:
            return 0

        client = _get_client()
        _ensure_collection(client)

        needs_refresh = True
        if not force:
            try:
                count = client.count(collection_name=COLLECTION_NAME).count
                if count >= len(records):
                    needs_refresh = False
            except Exception:
                needs_refresh = True

        if needs_refresh:
            _upsert_records(client, records)
            written = len(records)
        else:
            written = 0

        _dataset_synced = True
        return written


def _format_similar(payload: dict) -> str:
    name = payload.get("company") or "Unknown startup"
    details = [payload.get("industry"), payload.get("country"), payload.get("status")]
    descriptor = " • ".join(filter(None, details))
    valuation = payload.get("valuation_billion")
    if valuation:
        descriptor = (
            f"{descriptor} • ${valuation:.1f}B"
            if descriptor
            else f"${valuation:.1f}B"
        )
    return f"{name} ({descriptor})" if descriptor else name


def _score_to_similarity(score: float | None) -> float:
    if score is None:
        return 0.0
    # qdrant returns cosine similarity in [-1, 1], map to [0, 1]
    return max(0.0, min(1.0, (score + 1) / 2))


def find_similar_startups(idea: str, limit: int = 5) -> List[SimilarItem]:
    records = _dataset_records()
    if not records:
        return []

    try:
        sync_dataset()
        client = _get_client()
        query_vector = embed_text(idea)
        if not query_vector:
            return []

        hits = client.search(
            collection_name=COLLECTION_NAME,
            query_vector=query_vector,
            limit=limit,
            with_payload=True,
        )
    except Exception:
        return []

    similar: List[SimilarItem] = []
    for hit in hits:
        payload = hit.payload or {}
        similar.append(
            SimilarItem(
                idea=_format_similar(payload),
                similarity=_score_to_similarity(hit.score),
            )
        )
    return similar


if __name__ == "__main__":
    count = sync_dataset(force=True)
    print(f"Pushed {count} startups into Qdrant.")
