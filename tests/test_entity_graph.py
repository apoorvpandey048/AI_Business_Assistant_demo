"""Phase 3 — entity index, knowledge graph, cross-source coverage.

Locks the "everything about X across all sources" and "connected-fact recall"
guarantees, and the cross-source identity bridge that brings the SQLite 'CRM' under the
no-loss umbrella. Unit tests for the index / graph / ranker always run; the engine-level
cross-source tests rely on the seed corpus + seed DB shipped in the repo.

Run:  .venv/bin/python -m pytest tests/test_entity_graph.py -q
"""
from __future__ import annotations

import pytest

from app.retrieval.entity_index import EntityIndex, normalize_entity
from app.retrieval.fusion import reciprocal_rank_fusion, weighted_rank_fusion
from app.retrieval.graph import build_graph, chunk_node, ent_node
from app.retrieval.graph_retriever import graph_expand


# --- entity index ------------------------------------------------------------------
def test_normalize_drops_honorific_and_casefolds():
    assert normalize_entity("Dr.  Richard  Hall") == normalize_entity("richard hall")


def test_index_unions_chunk_and_row_into_one_entity():
    ei = EntityIndex()
    ei.add_chunk("c1", {"entities": ["Acme Corporation"]})
    ei.add_row("customers", "Acme Corporation",
               {"name": "Acme Corporation", "country": "USA"})
    rec = ei.lookup("acme corporation")
    assert rec is not None
    assert rec.chunk_ids == {"c1"} and rec.row_refs == {"customers#Acme Corporation"}
    assert rec.sources == {"documents", "relational"}     # cross-source bridge
    assert rec.as_dict()["cross_source"] is True


def test_index_skips_opaque_numeric_ids():
    ei = EntityIndex()
    ei.add_row("invoices", "INV-1", {"id": 1, "customer_id": 5, "invoice_ref": "INV-1"})
    # numeric id / customer_id are opaque keys, not entities; the ref is an entity
    assert ei.lookup("1") is None and ei.lookup("5") is None
    assert ei.lookup("INV-1") is not None


def test_mentions_for_returns_all_sources():
    ei = EntityIndex()
    ei.add_chunk("c1", {"entities": ["Globex Industries"]})
    ei.add_chunk("c2", {"entities": ["Globex Industries"]})
    ei.add_row("customers", "Globex Industries", {"name": "Globex Industries"})
    m = ei.mentions_for("globex industries")
    assert m["chunk_ids"] == ["c1", "c2"]
    assert m["row_refs"] == ["customers#Globex Industries"]


# --- graph -------------------------------------------------------------------------
def _toy_graph():
    ei = EntityIndex()
    ei.add_chunk("c1", {"entities": ["Acme Corporation", "Richard Hall"]})
    ei.add_chunk("c2", {"entities": ["Richard Hall"]})   # connected via Hall, not Acme
    ei.add_row("customers", "Acme Corporation", {"name": "Acme Corporation"})
    chunks = {
        "c1": {"chunk_id": "c1", "document": "d.pdf", "text": "Acme and Hall"},
        "c2": {"chunk_id": "c2", "document": "d.pdf", "text": "Hall again"},
    }
    return ei, build_graph(ei, chunks, owner_map={})


def test_graph_co_occurrence_links_entities():
    ei, g = _toy_graph()
    # Acme co-occurs with Hall in c1
    assert ent_node(normalize_entity("Richard Hall")) in \
        g.neighbors(ent_node("acme corporation"))


def test_graph_reaches_connected_chunk_without_shared_term():
    ei, g = _toy_graph()
    # starting from Acme, within 2 hops we reach c2 (Acme→Hall→c2) though c2 never
    # mentions Acme — the connected-fact recall the lexical search would miss
    reach = g.chunks_within(ent_node("acme corporation"), hops=2)
    assert chunk_node("c2") in reach


def test_graph_expand_returns_connected_chunks():
    ei, g = _toy_graph()
    out = graph_expand("Acme Corporation", g, ei, hops=2, limit=10)
    assert "c2" in out               # reached purely through the graph


def test_graph_expand_empty_for_unknown_entity():
    ei, g = _toy_graph()
    assert graph_expand("Nonexistent Entity Xyz", g, ei) == []


# --- unified ranker ----------------------------------------------------------------
def test_weighted_fusion_reduces_to_rrf_at_weight_one():
    lists = [["a", "b", "c"], ["b", "c", "d"]]
    plain = reciprocal_rank_fusion(lists, k=60)
    weighted = weighted_rank_fusion([(l, 1.0) for l in lists], k=60)
    assert plain == weighted


def test_weighted_fusion_downweights_auxiliary_signal():
    primary = ["a", "b"]
    aux = ["z"]            # only the low-weight signal ranks z
    scores = weighted_rank_fusion([(primary, 1.0), (aux, 0.3)], k=60)
    assert scores["a"] > scores["z"]      # primary top beats a down-weighted signal


# --- engine-level cross-source (seed corpus + seed DB) -----------------------------
def _engine_index():
    import os
    os.environ.setdefault("ABA_EMBEDDING_BACKEND", "hashing")
    from app.engine import Engine
    return Engine().document_source.index


def test_engine_builds_entity_graph():
    idx = _engine_index()
    if not idx.s.enable_entity_graph:
        pytest.skip("entity graph disabled")
    assert idx.graph is not None
    stats = idx.graph.stats()
    assert stats["entity"] > 0 and stats["chunk"] > 0


def test_engine_links_customer_across_pdf_and_db():
    idx = _engine_index()
    if not idx.s.enable_entity_graph:
        pytest.skip("entity graph disabled")
    # Acme Corporation appears in both a contract PDF and the customers table
    rec = idx.entities.lookup("Acme Corporation")
    assert rec is not None
    assert rec.chunk_ids and rec.row_refs       # present in BOTH sources
    assert rec.sources == {"documents", "relational"}
