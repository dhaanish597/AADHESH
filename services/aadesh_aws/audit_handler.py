"""Lambda entry point for the `Audit` state."""

from aadesh_aws.workflow_handlers import audit as handle

__all__ = ["handle"]
