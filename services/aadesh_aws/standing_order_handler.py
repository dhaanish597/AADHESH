"""Lambda entry point for the `Authorize` state: re-check the pre-commitment at fire time."""

from aadesh_aws.workflow_handlers import authorize_standing_order as handle

__all__ = ["handle"]
