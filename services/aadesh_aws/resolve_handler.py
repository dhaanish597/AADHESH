"""Lambda entry point for the `ResolveObligations` state."""

from aadesh_aws.workflow_handlers import resolve_obligations as handle

__all__ = ["handle"]
