"""Runtime wiring for the Aadesh Lambda functions.

Every handler in this package does the same three things and nothing else:

  1. read its configuration from the environment (here, once);
  2. build an `AadeshApplication` over the DynamoDB/S3 adapters (here, once);
  3. translate an event into a call, and a result into a reply.

Everything decision-shaped lives in `aadesh_core`; everything behaviour-shaped lives in
`aadesh_app`. If you find yourself writing an `if` about a GRAP stage or a parchi state in this
package, it belongs in one of those two instead.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from aadesh_adapters.audit.cloudwatch import CloudWatchAuditLog
from aadesh_adapters.authz.cedar_authz import CedarAuthorizationProvider
from aadesh_adapters.corpus.s3 import S3Corpus
from aadesh_adapters.store.dynamo import (
    DynamoAcknowledgementTokenStore,
    DynamoIdempotencyLedger,
    DynamoParchiStore,
    DynamoQrLinkCache,
    DynamoReadingsStore,
    DynamoSitesStore,
    DynamoStandingOrderStore,
    DynamoTaskTokenStore,
    DynamoTriggerRunStore,
)
from aadesh_app.application import AadeshApplication
from aadesh_cli.verify import run_verify
from aadesh_core.errors import AadeshError
from aadesh_core.explanation import SYSTEM_PROMPT
from aadesh_core.parchi_ack import Roster, RosterEntry


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def env_int(name: str, default: int) -> int:
    raw = env(name)
    return int(raw) if raw else default


@dataclass(frozen=True, slots=True)
class Config:
    site_id: str
    site_label: str
    supervisor_id: str
    facilitator_id: str
    worker_count: int
    registered_workers: int
    source_bucket: str
    corpus_prefix: str
    corpus_cache: Path
    explain_backend: str
    bedrock_region: str
    bedrock_model_id: str
    state_machine_arn: str
    event_bus_name: str
    environment: str

    @classmethod
    def from_env(cls) -> Config:
        return cls(
            site_id=env("AADESH_SITE_ID", "example-piling-site"),
            site_label=env("AADESH_SITE_LABEL", "Construction Site — Delhi-NCR"),
            supervisor_id=env("AADESH_SUPERVISOR_ID", "supervisor-001"),
            facilitator_id=env("AADESH_FACILITATOR_ID", "facilitator-001"),
            worker_count=env_int("AADESH_WORKER_COUNT", 34),
            registered_workers=env_int("AADESH_REGISTERED_WORKERS", 27),
            source_bucket=env("AADESH_SOURCE_BUCKET"),
            corpus_prefix=env("AADESH_CORPUS_PREFIX", "corpus"),
            corpus_cache=Path(env("AADESH_CORPUS_CACHE", "/tmp/aadesh-corpus")),
            explain_backend=env("AADESH_EXPLAIN_BACKEND", "deterministic"),
            bedrock_region=env("BEDROCK_REGION", "us-east-1"),
            bedrock_model_id=env("BEDROCK_MODEL_ID"),
            state_machine_arn=env("STEP_FUNCTIONS_ARN"),
            event_bus_name=env("AADESH_EVENT_BUS", "default"),
            environment=env("AADESH_ENV", "prod"),
        )


def build_roster(config: Config) -> Roster:
    return Roster(
        site_id=config.site_id,
        entries=tuple(
            RosterEntry(worker_id=f"worker-{i:03d}", display_name=f"Worker {i:03d}")
            for i in range(1, config.worker_count + 1)
        ),
    )


def registered_workers(config: Config) -> set[str]:
    return {f"worker-{i:03d}" for i in range(1, config.registered_workers + 1)}


def _explanation_model_factory(config: Config):
    """A factory for the optional explanation model, or None for the deterministic path.

    Three backends, and the choice is recorded rather than guessed:

      * `deterministic` -- no model at all. This is the default, and it is never wrong.
      * `bedrock`       -- Amazon Bedrock (Converse API) rephrasing the computed result.
      * `strands_bedrock` -- a Bedrock model driven by a TOOL-FREE Strands agent. Strands is an
        agent framework, and an agent is one step away from having tools; the wrapper builds it
        with no tools at all, so it can explain and nothing else. When Strands is not installed
        the factory falls back to the direct Bedrock adapter rather than failing the request.

    The model is built lazily so a deployment that leaves the deterministic backend in place
    never imports a Bedrock client and never needs the IAM grant for one.
    """
    if config.explain_backend not in ("bedrock", "strands_bedrock"):
        return None
    if not config.bedrock_model_id:
        return None

    def factory() -> Any:
        from aadesh_adapters.explain.bedrock import BedrockExplanationModel

        if config.explain_backend == "strands_bedrock":
            try:
                from strands import Agent
                from strands.models import BedrockModel

                from aadesh_adapters.explain.strands import (
                    StrandsExplanationModel,
                )

                agent = Agent(
                    model=BedrockModel(
                        model_id=config.bedrock_model_id, region_name=config.bedrock_region
                    ),
                    system_prompt=SYSTEM_PROMPT,
                )
                return StrandsExplanationModel(agent=agent)
            except ImportError:
                # Documented fallback: the direct Bedrock adapter, which satisfies the same
                # port. The status the user sees still says whether a model answered.
                pass

        return BedrockExplanationModel(
            model_id=config.bedrock_model_id,
            region_name=config.bedrock_region,
            temperature=float(env("BEDROCK_TEMPERATURE", "0.1") or 0.1),
            max_tokens=env_int("BEDROCK_MAX_TOKENS", 1024),
        )

    return factory


def load_site(config: Config):
    site = DynamoSitesStore().get(config.site_id)
    if site is None:
        raise AadeshError(
            f"Site {config.site_id!r} is not in the sites table. Deploy the corpus and the "
            f"site profile before serving traffic -- resolving obligations against a site "
            f"nobody described would be guessing."
        )
    return site


def build_application(config: Config | None = None) -> AadeshApplication:
    """Construct the application over the deployed adapters. One call per invocation."""
    config = config or Config.from_env()
    app = AadeshApplication(
        site=load_site(config),
        roster=build_roster(config),
        registered=registered_workers(config),
        store=DynamoParchiStore(),
        tokens=DynamoAcknowledgementTokenStore(),
        ledger=DynamoIdempotencyLedger(),
        authz=CedarAuthorizationProvider(
            policy_path=Path(env("AADESH_CEDAR_POLICY_PATH", _bundled("policies.cedar"))),
            denials_path=Path(env("AADESH_CEDAR_DENIALS_PATH", _bundled("denials.json"))),
            schema_path=Path(env("AADESH_CEDAR_SCHEMA_PATH", _bundled("schema.cedarschema.json"))),
        ),
        corpus=lambda: S3Corpus(
            bucket=config.source_bucket, prefix=config.corpus_prefix, cache_root=config.corpus_cache
        ),
        audit=CloudWatchAuditLog(),
        site_id=config.site_id,
        site_label=config.site_label,
        supervisor_id=config.supervisor_id,
        facilitator_id=config.facilitator_id,
        corpus_root=config.corpus_cache,
        verify_runner=run_verify,
        # Note the ports installed here, and the ones deliberately absent: there is no
        # in-memory store behind any of them, so nothing can silently degrade to a local
        # cache in production.
        order_store=DynamoStandingOrderStore(),
        trigger_runs=DynamoTriggerRunStore(),
        task_tokens=DynamoTaskTokenStore(),
        qr_cache=DynamoQrLinkCache(),
        readings_store=DynamoReadingsStore(),
        explanation_model_factory=_explanation_model_factory(config),
    )
    app.install_execution_resumer(_make_resumer())
    return app


def _bundled(name: str) -> str:
    """The Cedar artefacts ship inside the Lambda package, so every environment runs the SAME
    policy set. A policy file read from S3 could be swapped without a deploy; bundling makes
    the authorization boundary part of the artefact that was reviewed."""
    return str(Path(__file__).parent / "cedar" / name)


def _make_resumer():
    def resumer(task_token: str, parchi: Any) -> None:
        import boto3

        client = boto3.client("stepfunctions", region_name=env("AWS_REGION", "ap-south-1"))
        try:
            client.send_task_success(
                taskToken=task_token,
                output=(
                    f'{{"parchi_id": "{parchi.parchi_id}", '
                    f'"worker_id": "{parchi.worker_id}", "acknowledged": true}}'
                ),
            )
        except Exception:
            # The machine may already have timed out, or its task token may have expired. A
            # worker's acknowledgement is a fact regardless, and it has already been written;
            # failing the request here would tell the worker their confirmation did not count.
            return

    return resumer


def now() -> datetime:
    return datetime.now(UTC)


def token_ttl() -> timedelta:
    return timedelta(seconds=env_int("AADESH_QR_TOKEN_TTL_SECONDS", 86400))
