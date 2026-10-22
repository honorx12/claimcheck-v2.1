from app import retrieve, repo


def test_terms_safe_and_capped():
    t = retrieve.terms("Room rent; DROP TABLE x -- 'or' 1=1 " + " ".join(f"w{i:03d}" for i in range(100)))
    assert all(x.isalnum() for x in t) and len(t) <= 40 and "drop" in t   # words kept, punctuation gone


def test_search_embeds_original_and_ors_terms(monkeypatch):
    seen = {}
    monkeypatch.setattr(retrieve, "embed", lambda texts: [[0.1] * 384])
    monkeypatch.setattr(repo, "search_chunks", lambda uid, doc, q, emb, k: seen.update(uid=uid, doc=doc, q=q) or [])
    retrieve.search("u1", "d1", "Room rent cosmetic")
    assert seen == {"uid": "u1", "doc": "d1", "q": "cosmetic or rent or room"}


def test_sql_is_parameterised_and_scoped():
    s = repo.HYBRID_SQL
    assert s.count("user_id=%(uid)s") == 2 and s.count("document_id=%(doc)s") == 2 and "%(q)s" in s
    assert "<=>" in s and "websearch_to_tsquery" in s
