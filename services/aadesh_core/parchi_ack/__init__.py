"""Worker parchi acknowledgement: the opaque QR, the explicit confirm, and the sealed record.

The package's job in one line: turn "a deterministic compliance workflow says this worker was
displaced" into "this worker confirmed it, and here is immutable evidence of that".

What a parchi is NOT, and this module will not help you pretend otherwise:

  * not a payment, and not a claim on any government scheme
  * not a guarantee of compensation
  * not legal advice
  * not a determination that a worker is entitled to any particular sum
  * not a substitute for the CAQM order it cites

There is no verified monetary entitlement amount in the authoritative corpus, so nothing here
computes, stores or implies one. `entitlement_refs` are references to CITED clauses, and a
ref may have no amount at all -- that is the normal case, not a gap to be filled in later.

The moving parts:

  * `tokens`    -- mint and parse the opaque `aadesh://ack/<token>`, and the QR built on it
  * `events`    -- the `ParchiAcknowledged` audit record
  * `roster`    -- the minimal worker roster this workflow needs, and nothing more
  * `workflow`  -- creation, keyed on an idempotency key, and the Prompt 4 integration contract
  * `service`   -- the explicit confirm, and the seal that freezes the result

Nothing in this package imports a model, a network client or an AWS SDK, and
`tests/unit/test_parchi_no_model.py` asserts that.
"""

from __future__ import annotations

from aadesh_core.parchi_ack.events import (
    EVENT_TYPE_PARCHI_ACKNOWLEDGED,
    EVENT_TYPE_PARCHI_SEALED,
    PARCHI_EVENT_SCHEMA_VERSION,
    ParchiAcknowledged,
    ParchiSealed,
)
from aadesh_core.parchi_ack.roster import Roster, RosterEntry
from aadesh_core.parchi_ack.service import (
    AcknowledgementOutcome,
    PendingParchiView,
    acknowledge_parchi,
    describe_pending_parchi,
    seal_parchi,
)
from aadesh_core.parchi_ack.tokens import (
    TOKEN_SCHEME,
    AcknowledgementQr,
    AcknowledgementToken,
    TokenState,
    hash_token,
    mint_acknowledgement_token,
    parse_acknowledgement_payload,
)
from aadesh_core.parchi_ack.workflow import (
    ParchiIssue,
    ParchiProvenance,
    WorkflowExecution,
    create_parchi_for_worker,
    create_parchis_for_roster,
    issue_acknowledgement_qr,
)

__all__ = [
    "EVENT_TYPE_PARCHI_ACKNOWLEDGED",
    "EVENT_TYPE_PARCHI_SEALED",
    "PARCHI_EVENT_SCHEMA_VERSION",
    "TOKEN_SCHEME",
    "AcknowledgementOutcome",
    "AcknowledgementQr",
    "AcknowledgementToken",
    "ParchiAcknowledged",
    "ParchiIssue",
    "ParchiProvenance",
    "ParchiSealed",
    "PendingParchiView",
    "Roster",
    "RosterEntry",
    "TokenState",
    "WorkflowExecution",
    "acknowledge_parchi",
    "create_parchi_for_worker",
    "create_parchis_for_roster",
    "describe_pending_parchi",
    "hash_token",
    "issue_acknowledgement_qr",
    "mint_acknowledgement_token",
    "parse_acknowledgement_payload",
    "seal_parchi",
]
