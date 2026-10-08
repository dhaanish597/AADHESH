"""Authorization: the boundary between a request and a domain operation.

`resources` translates domain objects into the entities Cedar evaluates. `service` is the
protected surface a handler calls, so that "authorize, then act" is one step rather than a
convention each caller has to remember.
"""

from aadesh_core.authorization.resources import (
    claim_assistance_resource,
    parchi_resource,
    site_resource,
    to_epoch_seconds,
)
from aadesh_core.authorization.service import AuthorizationService

__all__ = [
    "AuthorizationService",
    "claim_assistance_resource",
    "parchi_resource",
    "site_resource",
    "to_epoch_seconds",
]
