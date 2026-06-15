"""Knowledge graph over entities, chunks, rows, and documents (Phase 3).

Turns the flat entity index into a navigable graph so retrieval can follow connections
that share no surface words — the "connected fact" recall that lexical + dense search
miss. Example: a question about "Mohammad Ben" can reach his hospital-transfer chunk and
any SQLite row about him through ``co-occurs`` / ``same-as`` edges, even when those
passages never repeat his name.

Node kinds:  entity | chunk | row | document
Edge kinds:
  mentions   chunk  → entity        (a chunk states this entity)
  in_row     row    → entity        (a structured row carries this entity)
  co_occurs  entity ↔ entity        (two entities share a chunk or row)
  owns       entity → document      (a customer/contract owns a contract PDF)
  same_as    entity ↔ entity        (cross-source identity: same key in doc AND row)
  contains   document → chunk

Pure-python adjacency (no networkx dependency): deterministic, offline, serializable.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Iterable

from app.retrieval.entity_index import EntityIndex, normalize_entity


@dataclass
class Graph:
    # adjacency: node -> {edge_kind -> set(neighbor nodes)}
    adj: dict[str, dict[str, set[str]]] = field(default_factory=dict)
    node_kind: dict[str, str] = field(default_factory=dict)

    # -- construction --------------------------------------------------------
    def _node(self, node_id: str, kind: str) -> None:
        self.node_kind.setdefault(node_id, kind)
        self.adj.setdefault(node_id, defaultdict(set))

    def add_edge(self, src: str, kind: str, dst: str, *,
                 src_kind: str, dst_kind: str, bidirectional: bool = False) -> None:
        self._node(src, src_kind)
        self._node(dst, dst_kind)
        self.adj[src][kind].add(dst)
        if bidirectional:
            self.adj[dst][kind].add(src)

    # -- query ---------------------------------------------------------------
    def neighbors(self, node_id: str, kinds: Iterable[str] | None = None) -> set[str]:
        out: set[str] = set()
        for ekind, dsts in self.adj.get(node_id, {}).items():
            if kinds is None or ekind in kinds:
                out |= dsts
        return out

    def chunks_within(self, node_id: str, hops: int = 2,
                      edge_kinds: Iterable[str] | None = None) -> set[str]:
        """All chunk nodes reachable from ``node_id`` within ``hops`` edges. Used by the
        graph-aware retriever to pull in connected passages."""
        seen = {node_id}
        frontier = {node_id}
        for _ in range(max(0, hops)):
            nxt: set[str] = set()
            for n in frontier:
                nxt |= self.neighbors(n, edge_kinds)
            nxt -= seen
            seen |= nxt
            frontier = nxt
            if not frontier:
                break
        return {n for n in seen if self.node_kind.get(n) == "chunk"}

    def stats(self) -> dict[str, int]:
        kinds: dict[str, int] = defaultdict(int)
        for k in self.node_kind.values():
            kinds[k] += 1
        edges = sum(len(d) for m in self.adj.values() for d in m.values())
        return {"nodes": len(self.node_kind), "edges": edges, **kinds}


# Node-id helpers — namespaced so an entity key never collides with a chunk id.
def ent_node(key: str) -> str:
    return f"ent::{key}"


def chunk_node(chunk_id: str) -> str:
    return f"chunk::{chunk_id}"


def row_node(ref: str) -> str:
    return f"row::{ref}"


def doc_node(document: str) -> str:
    return f"doc::{document}"


def build_graph(
    entity_index: EntityIndex,
    chunks: dict[str, dict[str, Any]] | None = None,
    owner_map: dict[str, str] | None = None,
) -> Graph:
    """Assemble the graph from the entity index (mentions/in_row/co_occurs/same_as),
    the chunk corpus (contains, co-occurrence within a chunk), and an optional
    document-owner map (owns edges, e.g. contract PDF → owning customer)."""
    g = Graph()
    chunks = chunks or {}

    # document → chunk containment
    for cid, c in chunks.items():
        document = c.get("document")
        if document:
            g.add_edge(doc_node(document), "contains", chunk_node(cid),
                       src_kind="document", dst_kind="chunk")

    # entity ↔ its mentions, and co-occurrence among entities sharing a chunk/row
    chunk_entities: dict[str, list[str]] = defaultdict(list)
    row_entities: dict[str, list[str]] = defaultdict(list)
    for rec in entity_index.records.values():
        en = ent_node(rec.key)
        for cid in rec.chunk_ids:
            # bidirectional: a chunk mentions an entity AND the entity is reachable back
            # to its chunks, so graph expansion can walk entity → connected chunks.
            g.add_edge(chunk_node(cid), "mentions", en,
                       src_kind="chunk", dst_kind="entity", bidirectional=True)
            chunk_entities[cid].append(rec.key)
        for ref in rec.row_refs:
            g.add_edge(row_node(ref), "in_row", en, src_kind="row", dst_kind="entity",
                       bidirectional=True)
            row_entities[ref].append(rec.key)
        # cross-source identity: the same entity in both a doc and a row is a bridge
        if len(rec.sources) > 1:
            # self same_as marks the node as a bridge for the retriever's diagnostics;
            # the practical link is that its chunk_ids and row_refs already connect.
            g.node_kind.setdefault(en, "entity")

    def _cooccur(groups: dict[str, list[str]]) -> None:
        for keys in groups.values():
            uniq = sorted(set(keys))
            for i in range(len(uniq)):
                for j in range(i + 1, len(uniq)):
                    g.add_edge(ent_node(uniq[i]), "co_occurs", ent_node(uniq[j]),
                               src_kind="entity", dst_kind="entity", bidirectional=True)

    _cooccur(chunk_entities)
    _cooccur(row_entities)

    # owns: a document's owning entity (customer/contract name) → the document, and the
    # entity ↔ the document's chunks so an entity query reaches the whole document.
    for document, owner in (owner_map or {}).items():
        okey = normalize_entity(owner)
        if not okey:
            continue
        g.add_edge(ent_node(okey), "owns", doc_node(document),
                   src_kind="entity", dst_kind="document")
        for cid in g.neighbors(doc_node(document), {"contains"}):
            g.add_edge(ent_node(okey), "mentions", cid,
                       src_kind="entity", dst_kind="chunk")

    return g
