#!/usr/bin/env python
"""Seed a deployed Aadesh stack with the data it refuses to run without.

Why this exists as a script rather than a hand-typed `aws dynamodb put-item`: the records it
writes are the records the *adapters* read. It serialises the site through `ConstructionSite`
and the reading through `DynamoReadingsStore.put` -- the same code path the deployed Lambda
uses -- so a seeded reading is a reading the Lambda can actually reconstruct. A hand-written
item that is one field off looks correct in the console and then fails inside `loads()` on the
deployed function, which is the worst place to find out.

Nothing here is a secret and nothing here invents a measurement:

  * the site profile is the committed fixture, verbatim;
  * the reading is the January 2026 replay observation, written by `replay_placeholder` and
    therefore labelled `provenance=replay`. It is evidence, never a stage input, and it is
    deliberately NOT labelled MEASURED -- no AQI source is configured in this deployment;
  * the demo users' passwords are generated (or taken from AADESH_DEMO_PASSWORD) and printed
    once. They are never written into the repository.

Usage (boto3 is the opt-in `aws` extra, so run it with one that has it):

    uv run --with boto3 python infra/aws/seed_aws.py all --stack-name aadesh-prod
    uv run --with boto3 python infra/aws/seed_aws.py check --stack-name aadesh-prod
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import string
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SITE_FIXTURE = REPO_ROOT / "fixtures" / "sites" / "piling-site.json"

#: The station the API reads (`AADESH_STATION_ID` in the template) and the parameter the
#: January replay's observation is for.
DEFAULT_STATION_ID = "DL-NCR-ROHINI-01"
DEFAULT_PARAMETER = "PM2.5"
REPLAY_VALUE = 285.0
REPLAY_OBSERVED_AT = datetime(2026, 1, 16, 8, 0, tzinfo=UTC)
REPLAY_INGESTED_AT = datetime(2026, 1, 16, 8, 5, tzinfo=UTC)

#: The three principals the authorization boundary reasons about. `principal_id` is the stable
#: identity a Parchi names -- `resource.worker == principal` is entity equality on it, so a
#: Cognito `sub` UUID can never stand in for it.
DEMO_USERS = (
    {
        "email": "supervisor@aadesh.example",
        "role": "supervisor",
        "principal_id": "supervisor-001",
        "assigned_site": "example-piling-site",
    },
    {
        "email": "facilitator@aadesh.example",
        "role": "facilitator",
        "principal_id": "facilitator-001",
        "assigned_site": None,
    },
    {
        "email": "worker@aadesh.example",
        "role": "worker",
        "principal_id": "worker-001",
        "assigned_site": None,
    },
)


def _wire_table_names(stack_name: str) -> None:
    """Point the adapters at this stack's physical tables before they are imported."""
    for suffix in (
        "parchis",
        "operational",
        "standing-orders",
        "trigger-runs",
        "readings",
        "sites",
    ):
        env = "AADESH_TABLE_" + suffix.upper().replace("-", "_")
        os.environ.setdefault(env, f"{stack_name}-{suffix}")
    os.environ.setdefault("AWS_REGION", "ap-south-1")


# --------------------------------------------------------------------------- site


def seed_site(*, site_id: str | None, fixture: Path) -> dict:
    from aadesh_core.domain.construction import ConstructionSite

    from aadesh_adapters.store.dynamo import DynamoSitesStore

    payload = json.loads(fixture.read_text(encoding="utf-8"))
    if site_id:
        payload["site_id"] = site_id
    site = ConstructionSite.from_dict(payload)
    DynamoSitesStore().save(site)
    return {
        "table": "sites",
        "site_id": site.site_id,
        "facts": len([v for v in payload.values() if v is not None]),
        "source": str(fixture.relative_to(REPO_ROOT)),
    }


# --------------------------------------------------------------------------- reading


def seed_reading(*, station_id: str, parameter: str) -> dict:
    from aadesh_adapters.store.dynamo import DynamoReadingsStore
    from aadesh_adapters.store.dynamo.readings import replay_placeholder

    reading = replay_placeholder(
        station_id=station_id,
        parameter=parameter,
        value=REPLAY_VALUE,
        observed_at=REPLAY_OBSERVED_AT,
        ingested_at=REPLAY_INGESTED_AT,
    )
    DynamoReadingsStore().put(reading)
    return {
        "table": "readings",
        "station_id": reading.station_id,
        "parameter": reading.parameter,
        "value": reading.value,
        "observed_at": reading.observed_at.isoformat(),
        "provenance": reading.provenance.value,
        "note": (
            "The January 2026 replay observation, labelled replay. No AQI provider is "
            "configured in this deployment, so nothing here is a live measurement."
        ),
    }


# --------------------------------------------------------------------------- users


def _password() -> str:
    """A policy-satisfying password: 12+ chars with upper, lower, digit and symbol.

    Generated unless AADESH_DEMO_PASSWORD is set, because a password that is committed is a
    password that is public -- and `test_no_committed_secrets.py` would rightly fail the build.
    """
    provided = os.environ.get("AADESH_DEMO_PASSWORD", "").strip()
    if provided:
        return provided
    alphabet = string.ascii_letters + string.digits
    body = "".join(secrets.choice(alphabet) for _ in range(14))
    return f"{body}!Aa1"


def seed_users(*, user_pool_id: str, password: str | None) -> dict:
    import boto3

    client = boto3.client("cognito-idp", region_name=os.environ.get("AWS_REGION", "ap-south-1"))
    secret = password or _password()
    created: list[dict] = []

    for user in DEMO_USERS:
        attributes = [
            {"Name": "email", "Value": user["email"]},
            {"Name": "email_verified", "Value": "true"},
            {"Name": "custom:role", "Value": user["role"]},
            {"Name": "custom:principal_id", "Value": user["principal_id"]},
        ]
        if user["assigned_site"]:
            attributes.append(
                {"Name": "custom:assigned_site", "Value": user["assigned_site"]}
            )

        try:
            client.admin_create_user(
                UserPoolId=user_pool_id,
                Username=user["email"],
                UserAttributes=attributes,
                MessageAction="SUPPRESS",  # no invite email; this is a seeded demonstration user
            )
        except client.exceptions.UsernameExistsException:
            # Re-running the seed must converge on the same users rather than fail. The
            # attributes are re-applied below, so a drifted role or site is corrected.
            client.admin_update_user_attributes(
                UserPoolId=user_pool_id, Username=user["email"], UserAttributes=attributes
            )

        client.admin_set_user_password(
            UserPoolId=user_pool_id,
            Username=user["email"],
            Password=secret,
            Permanent=True,  # not FORCE_CHANGE_PASSWORD: the admin API owns the credential
        )
        created.append(
            {
                "email": user["email"],
                "role": user["role"],
                "principal_id": user["principal_id"],
                "assigned_site": user["assigned_site"],
            }
        )

    return {"user_pool_id": user_pool_id, "password": secret, "users": created}


# --------------------------------------------------------------------------- check


def check(*, site_id: str, station_id: str) -> dict:
    """Read the seeded records back through the adapters the deployed Lambda uses."""
    from aadesh_adapters.store.dynamo import DynamoReadingsStore, DynamoSitesStore

    site = DynamoSitesStore().get(site_id)
    reading = DynamoReadingsStore().latest(station_id)
    return {
        "site": (
            {
                "site_id": site.site_id,
                "activity_type": site.activity_type,
                "in_ncr": site.in_ncr,
                "plot_size_sqm": site.plot_size_sqm,
            }
            if site
            else None
        ),
        "reading": (
            {
                "station_id": reading.station_id,
                "parameter": reading.parameter,
                "value": reading.value,
                "observed_at": reading.observed_at.isoformat(),
                "provenance": reading.provenance.value,
            }
            if reading
            else None
        ),
    }


# --------------------------------------------------------------------------- cli


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("action", choices=["site", "reading", "users", "all", "check"])
    parser.add_argument("--stack-name", default="aadesh-prod")
    parser.add_argument("--site-id", default="example-piling-site")
    parser.add_argument("--site-fixture", type=Path, default=DEFAULT_SITE_FIXTURE)
    parser.add_argument("--station-id", default=DEFAULT_STATION_ID)
    parser.add_argument("--parameter", default=DEFAULT_PARAMETER)
    parser.add_argument(
        "--user-pool-id",
        default=os.environ.get("AADESH_USER_POOL_ID", ""),
        help="required for the users action",
    )
    parser.add_argument("--credentials-out", type=Path, default=None)
    args = parser.parse_args(argv)

    _wire_table_names(args.stack_name)
    sys.path.insert(0, str(REPO_ROOT / "services"))

    result: dict = {"stack": args.stack_name, "region": os.environ["AWS_REGION"]}

    if args.action in ("site", "all"):
        result["site"] = seed_site(site_id=args.site_id, fixture=args.site_fixture)
    if args.action in ("reading", "all"):
        result["reading"] = seed_reading(
            station_id=args.station_id, parameter=args.parameter
        )
    if args.action in ("users", "all"):
        if not args.user_pool_id:
            print(
                "error: --user-pool-id (or AADESH_USER_POOL_ID) is required for `users`.",
                file=sys.stderr,
            )
            return 2
        result["users"] = seed_users(user_pool_id=args.user_pool_id, password=None)
    if args.action in ("check", "all"):
        result["check"] = check(site_id=args.site_id, station_id=args.station_id)

    if args.credentials_out and "users" in result:
        # Operator-local only. This path is gitignored; the script never writes it for you
        # unless asked, and never puts a password anywhere else.
        args.credentials_out.parent.mkdir(parents=True, exist_ok=True)
        args.credentials_out.write_text(json.dumps(result["users"], indent=2), encoding="utf-8")
        result["users"] = {**result["users"], "password": "<written to --credentials-out>"}

    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
