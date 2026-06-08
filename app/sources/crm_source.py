"""Stubbed FUTURE source — makes the extensibility claim concrete.

This implements the same Source interface as the live PDF and SQLite sources but is
marked `status="future"`. It demonstrates that adding CRM / email / cloud-storage
sources is a matter of implementing `describe()` + `retrieve()` and registering the
source — the router and orchestrator need no changes. It is intentionally NOT wired
into retrieval yet.
"""
from __future__ import annotations

from app.models import Evidence, SourceInfo


class CrmSource:
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
            details={"note": "Implements the Source interface; not enabled in the MVP demo."},
        )

    def retrieve(self, query: str, **_: object) -> list[Evidence]:  # pragma: no cover
        return []
