"""The one place the DynamoDB and S3 adapters touch boto3.

boto3 is imported lazily, inside the functions, for the same reason `adapters/explain/bedrock.py`
does it: it lives in the opt-in `aws` extra, and `make test` must run on a machine that has
never installed it.

`AWS_ENDPOINT_URL`, when set, is honoured by every client. That is what lets the same adapter
code run against LocalStack and against real AWS with no branch in the adapter itself -- the
`.env.example` documents this as the LocalStack switch.

The table names are physical, not logical, and come from the environment when the deployment
sets them (`AADESH_TABLE_*`). The defaults are the names the SAM template creates so a local
run against a deployed account works without extra configuration.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from types import MappingProxyType
from typing import Any

TABLES = MappingProxyType(
    {
        "parchis": "aadesh-parchis",
        "operational": "aadesh-operational",
        "standing_orders": "aadesh-standing-orders",
        "trigger_runs": "aadesh-trigger-runs",
        "readings": "aadesh-readings",
        "sites": "aadesh-sites",
    }
)

#: Logical name -> environment variable that overrides the physical table name.
TABLE_ENV = MappingProxyType(
    {
        "parchis": "AADESH_TABLE_PARCHIS",
        "operational": "AADESH_TABLE_OPERATIONAL",
        "standing_orders": "AADESH_TABLE_STANDING_ORDERS",
        "trigger_runs": "AADESH_TABLE_TRIGGER_RUNS",
        "readings": "AADESH_TABLE_READINGS",
        "sites": "AADESH_TABLE_SITES",
    }
)


class ConditionalCheckFailed(RuntimeError):
    """A conditional write lost its race.

    Adapters translate boto3's `ConditionalCheckFailedException` into this so no caller has to
    catch a `ClientError` and inspect a string to know that something already existed.
    """


class DynamoUnavailable(RuntimeError):
    """boto3 is not installed, or the table is unreachable. Never silently degraded."""


def table_name(logical: str) -> str:
    """The physical table name for a logical one, honouring the deployment's override."""
    env_var = TABLE_ENV.get(logical)
    if env_var:
        override = os.environ.get(env_var, "").strip()
        if override:
            return override
    return TABLES[logical]


def endpoint_url() -> str | None:
    """`AWS_ENDPOINT_URL` if set and non-blank, else None (real AWS)."""
    value = os.environ.get("AWS_ENDPOINT_URL", "").strip()
    return value or None


def region() -> str:
    return os.environ.get("AWS_REGION", "").strip() or "ap-south-1"


@contextmanager
def conditional_write() -> Iterator[None]:
    """Translate a lost conditional write into `ConditionalCheckFailed`.

    Every conditional `put_item` in this package wraps its call in this. boto3 signals a lost
    race by raising a `ClientError` whose `Error.Code` is the string
    `"ConditionalCheckFailedException"`; letting that escape would force every adapter -- and
    every caller -- to know that string. Any other error is re-raised unchanged, because
    translating a throttle into "already exists" would make a redelivered trigger skip work it
    never did instead of retrying it.
    """
    try:
        yield
    except Exception as exc:
        code = ""
        response = getattr(exc, "response", None)
        if isinstance(response, dict):
            code = str((response.get("Error") or {}).get("Code", ""))
        if getattr(exc, "code", "") == "ConditionalCheckFailedException" or (
            code == "ConditionalCheckFailedException"
        ):
            raise ConditionalCheckFailed(str(exc)) from exc
        raise


def _client(service: str) -> Any:
    try:
        import boto3
    except ImportError as exc:  # pragma: no cover -- exercised only without the aws extra
        raise DynamoUnavailable(
            'boto3 is not installed. Install the `aws` extra: `uv pip install -e ".[aws]"`.'
        ) from exc
    return boto3.client(service, region_name=region(), endpoint_url=endpoint_url())


def _resource(service: str) -> Any:
    try:
        import boto3
    except ImportError as exc:  # pragma: no cover -- exercised only without the aws extra
        raise DynamoUnavailable(
            'boto3 is not installed. Install the `aws` extra: `uv pip install -e ".[aws]"`.'
        ) from exc
    return boto3.resource(service, region_name=region(), endpoint_url=endpoint_url())


def dynamo_resource() -> Any:
    return _resource("dynamodb")


def dynamo_client() -> Any:
    return _client("dynamodb")


def s3_client() -> Any:
    return _client("s3")
