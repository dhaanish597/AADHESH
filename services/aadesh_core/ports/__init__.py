"""Ports: the only way the core reaches the outside world.

Every one of these is a `typing.Protocol`. The core depends on them; adapters satisfy them.
Nothing in `aadesh_core` imports boto3, requests, or any AWS SDK, and a Lambda handler and
the local HTTP server are both just adapters over the same calls.
"""

from __future__ import annotations

from aadesh_core.ports.aqi import AqiProvider
from aadesh_core.ports.audit import AuditLog
from aadesh_core.ports.authz import (
    AuthorizationDecision,
    AuthorizationProvider,
    AuthzResource,
    EntityRef,
)
from aadesh_core.ports.clock import Clock
from aadesh_core.ports.corpus import InvokedStageSource, RulesCorpus, SourceDocumentStore
from aadesh_core.ports.explanation import ExplanationModel, ExplanationProvider
from aadesh_core.ports.parchi_store import ParchiStore
from aadesh_core.ports.task_token import TaskTokenStore
from aadesh_core.ports.verification import CitationVerifier

__all__ = [
    "AqiProvider",
    "AuditLog",
    "AuthorizationDecision",
    "AuthorizationProvider",
    "AuthzResource",
    "CitationVerifier",
    "Clock",
    "EntityRef",
    "ExplanationModel",
    "ExplanationProvider",
    "InvokedStageSource",
    "ParchiStore",
    "RulesCorpus",
    "SourceDocumentStore",
    "TaskTokenStore",
]
