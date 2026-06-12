"""The source contract — the unified model every knowledge source plugs into.

A *source* is anything the assistant can draw evidence from. The router reads each
source's capability description (``describe()``) to decide where a question should
go, and the orchestrator collects fully-attributed ``Evidence`` from whichever
sources the route selects. Adding a new source — CRM, email, cloud storage, case
management — means subclassing ``BaseSource`` and registering the instance with the
engine; the router and orchestrator need no changes.

Hierarchy:

    BaseSource              identity + capability description (this module)
    ├── DocumentSource      unstructured text → hybrid retrieval (document_source.py)
    ├── StructuredSource    tabular records → schema-aware SQL (structured_source.py)
    └── CrmSource           roadmap example of an API-backed source (crm_source.py)

External systems connect through *connectors* (see ``app/sources/connectors``),
which sync or proxy third-party data into one of these source types.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from app.models import SourceInfo


class BaseSource(ABC):
    """Identity and self-description shared by every knowledge source.

    Subclasses add their retrieval surface: ``DocumentSource.retrieve()`` returns
    ranked text passages, ``StructuredSource.run()`` executes validated SQL. Both
    return ``Evidence`` — the traceability spine that the answer, citations, and
    inspector all reference.
    """

    #: Stable identifier used in evidence attribution and routing.
    name: str = "source"
    #: What kind of data this source serves: "documents" | "relational" | "api".
    kind: str = "documents"

    @abstractmethod
    def describe(self) -> SourceInfo:
        """What this source is and what it can answer — fed to the router.

        Descriptions must be *data-driven* (real table/document names), because the
        router's capability brief is rebuilt from them after every ingestion.
        """


def router_capability_brief(sources: list[SourceInfo]) -> str:
    """Compact, model-facing description of available sources for the classifier."""
    lines = []
    for s in sources:
        if s.status != "active":
            continue
        caps = "; ".join(s.capabilities)
        lines.append(f"- {s.name} ({s.kind}): {s.title}. {s.description} Answers: {caps}")
    return "\n".join(lines)
