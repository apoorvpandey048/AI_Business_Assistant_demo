"""Cross-source entity index (Phase 3).

Maps each distinctive entity — a person, organization, identifier, email, amount, or
date — to every place it appears: document chunks AND structured (CRM/SQLite) rows. This
is the substrate for "give me everything about X across all sources" and the node set of
the knowledge graph.

Built deterministically from:
- per-chunk metadata produced at ingest (``app.ingestion.metadata``), and
- structured rows, whose cell values are entities in their own right (a customer name,
  an invoice_ref, a contact_email).

Offline, no LLM. Entity keys are normalized (casefold + collapsed whitespace) so
"Dr. Richard Hall" in a PDF and "Richard Hall" in a row resolve to overlapping keys for
the graph's cross-source ``same-as`` linking.
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Iterable

_WS = re.compile(r"\s+")
_HONORIFIC = re.compile(r"^(?:dr|mr|mrs|ms|prof|hon|judge|rev)\.?\s+", re.I)
# Metadata buckets whose values are entities. (Excludes free-text fields.)
_ENTITY_FIELDS = ("entities", "identifiers", "emails", "amounts", "dates", "phones")


def normalize_entity(value: str) -> str:
    """Canonical key for an entity mention: casefolded, whitespace-collapsed, leading
    honorific dropped. ``"Dr.  Richard  Hall"`` and ``"richard hall"`` → same key."""
    v = _WS.sub(" ", (value or "").strip())
    v = _HONORIFIC.sub("", v)
    return v.casefold()


@dataclass
class EntityRecord:
    """Everywhere one entity appears."""
    key: str                                   # normalized
    display: str                               # first-seen surface form
    kind: str                                  # person|org|identifier|email|amount|date|value
    chunk_ids: set[str] = field(default_factory=set)
    row_refs: set[str] = field(default_factory=set)   # "table#rowkey"
    sources: set[str] = field(default_factory=set)    # "documents" | "relational"

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key, "display": self.display, "kind": self.kind,
            "chunk_ids": sorted(self.chunk_ids), "row_refs": sorted(self.row_refs),
            "sources": sorted(self.sources),
            "cross_source": len(self.sources) > 1,
        }


def _kind_of(field_name: str, value: str) -> str:
    return {
        "entities": "person_or_org", "identifiers": "identifier", "emails": "email",
        "amounts": "amount", "dates": "date", "phones": "phone",
    }.get(field_name, "value")


class EntityIndex:
    """Inverted index entity → {chunks, rows}. Append-only; rebuilt cheaply at ingest."""

    def __init__(self) -> None:
        self.records: dict[str, EntityRecord] = {}

    # -- build ---------------------------------------------------------------
    def add_chunk(self, chunk_id: str, metadata: dict[str, list[str]] | None) -> None:
        for fieldname in _ENTITY_FIELDS:
            for value in (metadata or {}).get(fieldname, []):
                rec = self._touch(value, _kind_of(fieldname, value))
                if rec is not None:
                    rec.chunk_ids.add(chunk_id)
                    rec.sources.add("documents")

    def add_chunks(self, chunks: Iterable[dict[str, Any]]) -> None:
        for c in chunks:
            self.add_chunk(c["chunk_id"], c.get("metadata"))

    def add_row(self, table: str, row_key: str, row: dict[str, Any],
                entity_columns: Iterable[str] | None = None) -> None:
        """Index a structured row. Cell values in ``entity_columns`` (default: all
        string-ish, non-numeric-id cells) become entities pointing at this row."""
        ref = f"{table}#{row_key}"
        cols = entity_columns if entity_columns is not None else row.keys()
        for col in cols:
            val = row.get(col)
            if val is None:
                continue
            sval = str(val).strip()
            if not sval or _is_opaque_id(col, sval):
                continue
            rec = self._touch(sval, _column_kind(col))
            if rec is not None:
                rec.row_refs.add(ref)
                rec.sources.add("relational")

    # -- query ---------------------------------------------------------------
    def lookup(self, value: str) -> EntityRecord | None:
        return self.records.get(normalize_entity(value))

    def mentions_for(self, value: str) -> dict[str, list[str]]:
        """All chunks + rows for an entity (everything-about-X across sources)."""
        rec = self.lookup(value)
        if rec is None:
            return {"chunk_ids": [], "row_refs": []}
        return {"chunk_ids": sorted(rec.chunk_ids), "row_refs": sorted(rec.row_refs)}

    def cross_source_entities(self) -> list[EntityRecord]:
        """Entities that appear in BOTH a document and a row — the same-as bridges."""
        return [r for r in self.records.values() if len(r.sources) > 1]

    @property
    def size(self) -> int:
        return len(self.records)

    # -- internal ------------------------------------------------------------
    def _touch(self, value: str, kind: str) -> EntityRecord | None:
        key = normalize_entity(value)
        if len(key) < 2:                       # too short to be a meaningful entity
            return None
        rec = self.records.get(key)
        if rec is None:
            rec = EntityRecord(key=key, display=_WS.sub(" ", value.strip()), kind=kind)
            self.records[key] = rec
        return rec


# Columns whose values are opaque numeric keys, not searchable entities.
_OPAQUE_ID_COLS = {"id", "customer_id", "contract_id", "invoice_id", "project_id"}


def _is_opaque_id(col: str, value: str) -> bool:
    return col.casefold() in _OPAQUE_ID_COLS and value.isdigit()


def _column_kind(col: str) -> str:
    c = col.casefold()
    if "email" in c:
        return "email"
    if c.endswith("_ref") or c == "sla_ref":
        return "identifier"
    if "date" in c:
        return "date"
    if "amount" in c or "value" in c or "usd" in c:
        return "amount"
    if c in ("name", "customer", "title"):
        return "person_or_org"
    return "value"
