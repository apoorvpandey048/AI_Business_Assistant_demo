"""Graph-aware retrieval expansion (Phase 3).

After the lexical + dense pass selects its passages, this expands the candidate set
along knowledge-graph edges: passages CONNECTED to the question's entities — through
co-occurrence, document ownership, or cross-source identity — that share no surface
words with the query and would otherwise be missed. This is the "connected fact" recall
that completes the no-loss guarantee.

Bounded and deterministic: it walks at most ``hops`` edges from the entities the query
names, returns the reachable chunk ids ranked by graph proximity, and the caller fuses
them into the ranking (it never silently replaces the lexical result).
"""
from __future__ import annotations

from app.retrieval.entity_index import EntityIndex, normalize_entity
from app.retrieval.graph import Graph, chunk_node, ent_node
from app.retrieval.intent import _distinctive_terms, content_terms


def _query_entities(query: str, index: EntityIndex) -> list[str]:
    """Entity keys the query references that exist in the index.

    Matches three ways, in order: (1) the exact query string; (2) distinctive spans /
    content terms looked up directly; (3) known multi-word entity keys all of whose
    tokens appear in the query ("Acme Corporation" matched from a query mentioning both
    "acme" and "corporation"). This bridges the gap between phrase-keyed entities and a
    loosely-phrased question."""
    keys: list[str] = []
    seen: set[str] = set()

    def _add(rec) -> None:
        if rec is not None and rec.key not in seen:
            seen.add(rec.key)
            keys.append(rec.key)

    _add(index.lookup(query))
    for term in list(_distinctive_terms(query)) + list(content_terms(query)):
        _add(index.lookup(term))

    # token-containment match for multi-word entities not caught above
    q_tokens = {t for t in normalize_entity(query).split() if len(t) > 1}
    if q_tokens:
        for rec in index.records.values():
            if rec.key in seen:
                continue
            key_tokens = [t for t in rec.key.split() if len(t) > 1]
            if len(key_tokens) >= 2 and all(t in q_tokens for t in key_tokens):
                _add(rec)
    return keys


def graph_expand(
    query: str, graph: Graph, index: EntityIndex, *,
    hops: int = 2, limit: int = 20,
) -> list[str]:
    """Chunk ids reachable from the query's entities within ``hops`` graph edges,
    ranked by proximity (1-hop before 2-hop), capped at ``limit``. Empty when the query
    names no known entity. The returned ids are raw chunk ids (node prefix stripped)."""
    ent_keys = _query_entities(query, index)
    if not ent_keys:
        return []

    seeds = {ent_node(k) for k in ent_keys}
    ranked: list[str] = []
    seen_chunks: set[str] = set()
    frontier = set(seeds)
    visited = set(seeds)
    for _ in range(max(1, hops)):
        nxt: set[str] = set()
        for node in frontier:
            for nb in graph.neighbors(node):
                if nb in visited:
                    continue
                visited.add(nb)
                nxt.add(nb)
                if graph.node_kind.get(nb) == "chunk":
                    cid = nb[len("chunk::"):] if nb.startswith("chunk::") else nb
                    if cid not in seen_chunks:
                        seen_chunks.add(cid)
                        ranked.append(cid)
                        if len(ranked) >= limit:
                            return ranked
        frontier = nxt
        if not frontier:
            break
    return ranked
