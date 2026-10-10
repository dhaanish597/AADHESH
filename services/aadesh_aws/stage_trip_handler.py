"""Lambda entry point for the `StageTrip` state.

One state, one function, so the execution history names the step that produced each fact.
"""

from aadesh_aws.workflow_handlers import stage_trip as handle

__all__ = ["handle"]
