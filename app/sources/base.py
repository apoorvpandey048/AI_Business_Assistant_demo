"""The Source contract.

The router reads each source's capability description to decide where a question
should go. Adding a new source (CRM, email, cloud storage) means implementing this
Protocol and registering it — the router and orchestrator need no changes.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.models import SourceInfo


@runtime_checkable
class Source(Protocol):
    name: str
    kind: str  # "documents" | "relational" | "api"

    def describe(self) -> SourceInfo:
        """What this source is and what it can answer — fed to the router."""
        ...


def router_capability_brief(sources: list[SourceInfo]) -> str:
    """Compact, model-facing description of available sources for the classifier."""
    lines = []
    for s in sources:
        if s.status != "active":
            continue
        caps = "; ".join(s.capabilities)
        lines.append(f"- {s.name} ({s.kind}): {s.title}. {s.description} Answers: {caps}")
    return "\n".join(lines)
