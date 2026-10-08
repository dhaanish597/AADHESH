"""Aadesh Standing Orders -- signed, narrow, time-bounded pre-commitments.

Load-bearing guarantees, stated so they can be tested:

  * A StandingOrder is a pre-commitment, not an autonomous-agent permission. The schema and the
    value object both refuse arbitrary code, prompts, instructions, scripts or templates.
  * Idempotency is structural: the dedupe key is a trigger fingerprint, and each parchi id is
    derived deterministically from (fingerprint, worker_id). Duplicate parchis become
    unrepresentable rather than checked-for.
  * Expiry is computed on demand, not by a frontend timer: `project_status` answers "what must
    the status be right now?" from the clock and the stored window, independent of what was
    persisted.
  * Authorization is not a signup-time boolean. The machine re-checks the recorded supervisor's
    authority at fire time, so a supervisor reassigned between signing and firing can no longer
    issue the halt they pre-committed to.
"""

from __future__ import annotations

from aadesh_core.standing_order.lifecycle import (
    IllegalStandingOrderTransition as IllegalStandingOrderTransition,
)
from aadesh_core.standing_order.lifecycle import (
    activate as activate,
)
from aadesh_core.standing_order.lifecycle import (
    complete as complete,
)
from aadesh_core.standing_order.lifecycle import (
    confirm as confirm,
)
from aadesh_core.standing_order.lifecycle import (
    expire as expire,
)
from aadesh_core.standing_order.lifecycle import (
    fire as fire,
)
from aadesh_core.standing_order.lifecycle import (
    project_status as project_status,
)
from aadesh_core.standing_order.models import (
    StageInvocationTrigger as StageInvocationTrigger,
)
from aadesh_core.standing_order.models import (
    StandingOrder as StandingOrder,
)
from aadesh_core.standing_order.models import (
    StandingOrderActionClause as StandingOrderActionClause,
)
from aadesh_core.standing_order.models import (
    TriggerRun as TriggerRun,
)
from aadesh_core.standing_order.models import (
    deterministic_parchi_id as deterministic_parchi_id,
)
from aadesh_core.standing_order.models import (
    trigger_fingerprint as trigger_fingerprint,
)
from aadesh_core.standing_order.trigger import (
    TriggerDecision as TriggerDecision,
)
from aadesh_core.standing_order.trigger import (
    TriggerRefusal as TriggerRefusal,
)
from aadesh_core.standing_order.trigger import (
    evaluate_trigger as evaluate_trigger,
)
