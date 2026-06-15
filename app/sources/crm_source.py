"""CRM source — customer-relationship data.

For this sprint the CRM data lives in the SQLite structured source (customers,
contracts, invoices, projects, payments), which IS the system of record for accounts
and renewals. Those rows are fully covered by the no-loss guarantee: they participate
in SQL retrieval, in the cross-source entity index, and in the knowledge graph (a
customer/contract that appears in both a row and a contract PDF is linked via a
``same-as`` bridge). This class describes that capability to the router.

A live external-CRM connector (Salesforce/HubSpot/etc.) is the post-MVP path: it syncs
into the same SQLite working database, after which all the existing routing / retrieval
/ citation machinery applies unchanged. See ``app/sources/connectors`` and
``docs/connectors.md``.
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
            title="CRM (accounts & renewals)",
            description=(
                "Customer relationship data — accounts, contracts, invoices, projects, "
                "and renewal stages. Backed by the structured database for this release "
                "and covered by the cross-source entity graph; a live external-CRM "
                "connector syncs into the same store post-MVP."
            ),
            capabilities=[
                "account / contract / invoice / project records and their relationships",
                "renewal stage, contract value, payment status",
                "cross-source links to the matching contract documents",
            ],
            status="future",
            details={"note": "SQLite-backed this sprint; external-CRM connector arrives via an adapter."},
        )

    def retrieve(self, query: str, **_: object) -> list[Evidence]:  # pragma: no cover
        # CRM rows are retrieved through the structured source + entity graph, not here.
        return []
