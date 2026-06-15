"""Read/write the cached recommendation result. The pipeline writes here; the
GET endpoint reads here so user-facing latency never includes the LLM."""
from __future__ import annotations
import json
from src.backend.initialize_database_schema import RecommendationCache


def write_cache(session, *, scope: str, payload: list, source: str) -> RecommendationCache:
    row = RecommendationCache(scope=scope, payload_json=json.dumps(payload), source=source)
    session.add(row)
    session.flush()
    return row


def read_latest_cache(session, *, scope: str = "household") -> dict | None:
    row = (
        session.query(RecommendationCache)
        .filter(RecommendationCache.scope == scope)
        .order_by(RecommendationCache.generated_at.desc(), RecommendationCache.id.desc())
        .first()
    )
    if not row:
        return None
    return {
        "source": row.source,
        "generated_at": row.generated_at.isoformat() if row.generated_at else None,
        "payload": json.loads(row.payload_json or "[]"),
    }
