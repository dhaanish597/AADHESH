"""Lambda entry point for the scheduled EventBridge ingestion rule."""

from aadesh_aws.workflow_handlers import ingest as handle

__all__ = ["handle"]
