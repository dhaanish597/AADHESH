"""DynamoDB adapters for every core persistence port.

The one entry point an application wires against is here, so a handler never has to know which
module a particular store lives in.
"""

from __future__ import annotations

from aadesh_adapters.store.dynamo.client import (
    ConditionalCheckFailed,
    DynamoUnavailable,
    dynamo_client,
    dynamo_resource,
    endpoint_url,
    s3_client,
    table_name,
)
from aadesh_adapters.store.dynamo.operational import (
    DynamoAcknowledgementTokenStore,
    DynamoIdempotencyLedger,
    DynamoQrLinkCache,
    DynamoTaskTokenStore,
)
from aadesh_adapters.store.dynamo.parchi import DynamoParchiStore
from aadesh_adapters.store.dynamo.readings import DynamoReadingsStore
from aadesh_adapters.store.dynamo.serde import SerdeError, dumps, loads
from aadesh_adapters.store.dynamo.sites import DynamoSitesStore
from aadesh_adapters.store.dynamo.standing_order import (
    DynamoStandingOrderStore,
    DynamoTriggerRunStore,
)

__all__ = [
    "ConditionalCheckFailed",
    "DynamoAcknowledgementTokenStore",
    "DynamoIdempotencyLedger",
    "DynamoParchiStore",
    "DynamoQrLinkCache",
    "DynamoReadingsStore",
    "DynamoSitesStore",
    "DynamoStandingOrderStore",
    "DynamoTaskTokenStore",
    "DynamoTriggerRunStore",
    "DynamoUnavailable",
    "SerdeError",
    "dumps",
    "dynamo_client",
    "dynamo_resource",
    "endpoint_url",
    "loads",
    "s3_client",
    "table_name",
]
