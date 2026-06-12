"""Connector contracts — how external systems plug into the source model.

See ``base.py`` for the interfaces and ``docs/connectors.md`` for the integration
guide covering the planned targets (Salesforce, HubSpot, Dynamics, Zoho, Gmail,
Outlook, SharePoint, Google Drive).
"""
from app.sources.connectors.base import (BaseConnector, ConnectorAuth,
                                         DocumentPayload, SyncResult, TablePayload)

__all__ = [
    "BaseConnector",
    "ConnectorAuth",
    "DocumentPayload",
    "SyncResult",
    "TablePayload",
]
