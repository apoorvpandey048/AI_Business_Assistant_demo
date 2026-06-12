"""Roadmap source — makes the extensibility claim concrete.

This implements the same BaseSource interface as the live document and structured
sources but is marked `status="future"`. It demonstrates that adding CRM / email /
cloud-storage sources is a matter of implementing `describe()` (plus a retrieval
surface) and registering the source — the router and orchestrator need no changes.
The concrete integration path lives in ``app/sources/connectors`` and
``docs/connectors.md``. It is intentionally NOT wired into retrieval yet.
"""
from __future__ import annotations

from app.models import Evidence, SourceInfo
from app.sources.base import BaseSource


class CrmSource(BaseSource):
    name = "crm"
    kind = "api"

    def describe(self) -> SourceInfo:
        return SourceInfo(
            name=self.name, kind="api",
            title="CRM (future integration)",
            description=(
                "Customer relationship data — accounts, contacts, opportunities, renewal "
                "stages. Planned post-MVP; shown here to demonstrate the connector pattern."
            ),
            capabilities=[
                "account owner / renewal stage / opportunity value",
                "contact and activity history",
            ],
            status="future",
            details={"note": "Implements the BaseSource interface; integration arrives via a connector adapter."},
        )

    def retrieve(self, query: str, **_: object) -> list[Evidence]:  # pragma: no cover
        return []
