"""Hybrid retrieval: embed (bge-small, 384-d) + keyword OR-terms, fused by RRF in SQL."""
import re
import threading

from . import repo

_model = None
_lock = threading.Lock()


def _get_model():
    global _model
    with _lock:
        if _model is None:
            from fastembed import TextEmbedding      # lazy: heavy import, keeps tests fast
            _model = TextEmbedding("BAAI/bge-small-en-v1.5")
        return _model


def embed(texts: list[str]) -> list[list[float]]:
    return [[float(x) for x in v] for v in _get_model().embed(texts)]


def terms(query: str, cap: int = 40) -> list[str]:
    """Safe keyword terms only ([a-z0-9]{3,}). websearch_to_tsquery ANDs words, so we OR them (Guide 14.2)."""
    return sorted(set(re.findall(r"[a-z0-9]{3,}", query.lower())))[:cap]


def search(uid: str, doc_id: str, query: str, k: int = 8) -> list[dict]:
    return repo.search_chunks(uid, doc_id, " or ".join(terms(query)), embed([query])[0], k)
