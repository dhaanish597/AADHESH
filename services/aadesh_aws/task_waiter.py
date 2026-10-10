"""Lambda entry point for the `AwaitWorkerAck` state (lambda:invoke.waitForTaskToken)."""

from aadesh_aws.workflow_handlers import worker_ack_waiter as handle

__all__ = ["handle"]
