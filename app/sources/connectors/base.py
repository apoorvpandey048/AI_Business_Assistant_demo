"""Connector adapter contracts (architecture only — no live integrations yet).

A *connector* moves data from an external system into one of the two retrieval
surfaces the engine already has:

- **Structured systems** (Salesforce, HubSpot, Dynamics, Zoho, case management)
  sync objects as *tables*. The engine merges them into the working SQLite
  database (the same path uploaded ``.db`` files take), after which schema-aware
  SQL, routing, and row-level citations apply with no further work.
- **Document systems** (Gmail, Outlook, SharePoint, Google Drive) sync items as
  *text documents*. The engine chunks and indexes them exactly like uploaded
  PDFs, after which hybrid retrieval and page/section citations apply.

So a connector never implements retrieval. It implements **extraction**: connect,
enumerate what changed, and emit ``TablePayload`` / ``DocumentPayload`` batches.
That keeps every adapter small and keeps all answering behavior — routing,
grounding, citation verification, the inspector trace — uniform across systems.

The contracts below are deliberately synchronous and batch-oriented (pull-based
incremental sync). Webhooks/streaming can be added per adapter later without
changing the engine side.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Iterator, Literal


@dataclass
class ConnectorAuth:
    """Authentication material for an external system.

    ``method`` declares which fields matter; secrets are provided via environment
    or a secret store and referenced here — never hardcoded and never sent to the
    browser (same rule as the model API key).
    """

    method: Literal["oauth2", "api_key", "basic"] = "oauth2"
    #: e.g. {"client_id": ..., "token_url": ...} — non-secret parameters only.
    params: dict[str, Any] = field(default_factory=dict)
    #: Name of the env var / secret-store key holding the credential.
    secret_ref: str = ""


@dataclass
class TablePayload:
    """One table of rows extracted from a structured system (CRM object, case list)."""

    name: str                                   # e.g. "sf_opportunities"
    columns: list[str]
    rows: list[dict[str, Any]]
    #: Stable per-row identifier column, used for incremental upserts.
    primary_key: str = "id"


@dataclass
class DocumentPayload:
    """One text document extracted from a document system (email, drive file)."""

    name: str                                   # e.g. "RE: renewal terms.eml"
    text: str
    #: Provenance shown in citations: {"folder": ..., "from": ..., "url": ...}
    metadata: dict[str, Any] = field(default_factory=dict)
    language: str | None = None                 # auto-detected when None


@dataclass
class SyncResult:
    """Outcome of one sync run — feeds the source inventory and the UI."""

    ok: bool
    tables: int = 0
    documents: int = 0
    rows: int = 0
    #: Opaque checkpoint passed back on the next sync (cursor, timestamp, …).
    cursor: str | None = None
    error: str | None = None


class BaseConnector(ABC):
    """The adapter contract every integration implements.

    Lifecycle: ``test_connection()`` once at registration, then periodic
    ``sync(cursor)`` calls. The engine consumes the emitted payloads:
    ``TablePayload`` batches merge into the working database (collision-safe,
    exactly like SQLite uploads) and refresh the ``StructuredSource`` schema;
    ``DocumentPayload`` batches are chunked and appended to the document index.
    After either, the router capability brief is rebuilt — the new data is
    immediately routable and citable.
    """

    #: Stable identifier, e.g. "salesforce", "gmail".
    system: str = ""
    #: Which retrieval surface this connector feeds.
    target: Literal["structured", "document"] = "structured"

    def __init__(self, auth: ConnectorAuth) -> None:
        self.auth = auth

    @abstractmethod
    def test_connection(self) -> bool:
        """Validate credentials and reachability without moving data."""

    @abstractmethod
    def sync(self, cursor: str | None = None) -> Iterator[TablePayload | DocumentPayload]:
        """Yield everything new/changed since ``cursor`` (None → full sync).

        Implementations should yield in modest batches so large mailboxes or
        CRMs ingest incrementally under the engine lock.
        """
