"""Vector knowledge base backed by LanceDB with feature-hashing embeddings (pure Python, no external API)."""
import re
from hashlib import md5

import lancedb
import numpy as np
import pyarrow as pa

from app.core.config import get_settings

_VECTOR_DIM = 384
_TABLE_NAME = "travel_knowledge"

_db: lancedb.DBConnection | None = None
_table: lancedb.table.Table | None = None

_SCHEMA = pa.schema([
    pa.field("id", pa.string()),
    pa.field("title", pa.string()),
    pa.field("content", pa.string()),
    pa.field("destination", pa.string()),
    pa.field("category", pa.string()),
    pa.field("vector", pa.list_(pa.float32(), _VECTOR_DIM)),
])


def _embed(text: str) -> list[float]:
    """Feature-hashing bag-of-words embedding normalised to unit length."""
    tokens = re.findall(r"[a-z]+", text.lower())
    vec = np.zeros(_VECTOR_DIM, dtype=np.float32)
    for token in tokens:
        idx = int(md5(token.encode()).hexdigest(), 16) % _VECTOR_DIM
        vec[idx] += 1.0
    norm = np.linalg.norm(vec)
    if norm > 0:
        vec /= norm
    return vec.tolist()


def _get_table() -> lancedb.table.Table:
    global _db, _table
    if _table is None:
        settings = get_settings()
        _db = lancedb.connect(settings.vector_store_path)
        existing = _db.table_names()
        if _TABLE_NAME in existing:
            _table = _db.open_table(_TABLE_NAME)
        else:
            _table = _db.create_table(_TABLE_NAME, schema=_SCHEMA)
    return _table


def add_entry(
    *,
    entry_id: str,
    title: str,
    content: str,
    destination: str = "",
    category: str = "",
) -> None:
    table = _get_table()
    vector = _embed(f"{title} {content}")

    try:
        table.delete(f"id = '{entry_id}'")
    except Exception:
        pass

    table.add([{
        "id": entry_id,
        "title": title,
        "content": content,
        "destination": destination,
        "category": category,
        "vector": vector,
    }])


def search(
    query: str,
    *,
    n_results: int = 5,
    destination_filter: str = "",
) -> list[dict]:
    table = _get_table()
    if table.count_rows() == 0:
        return []

    query_vector = np.array(_embed(query), dtype=np.float32)
    effective_n = min(n_results, table.count_rows())

    search_query = table.search(query_vector).limit(effective_n)
    if destination_filter:
        search_query = search_query.where(
            f"destination = '{destination_filter}'", prefilter=True
        )

    rows = search_query.to_list()
    return [
        {
            "id": r["id"],
            "title": r["title"],
            "content": r["content"],
            "destination": r["destination"],
            "category": r["category"],
            "distance": float(r.get("_distance", 0.0)),
        }
        for r in rows
    ]


def use_ephemeral_store() -> None:
    """Switch to a fresh in-memory store. Call from tests only."""
    global _db, _table
    import tempfile
    _db = lancedb.connect(tempfile.mkdtemp())
    _table = _db.create_table(_TABLE_NAME, schema=_SCHEMA)
