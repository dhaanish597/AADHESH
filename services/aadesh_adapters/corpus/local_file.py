"""Loads the rules corpus from disk, deriving source_state from a verification run.

This adapter is the join between provenance and resolution, and the single most
security-relevant file in the repo. Two rules:

  * `source_state` is computed, never read. A corpus file that tries to declare itself
    verified is rejected outright -- that would be the data asserting its own provenance.
  * Every entry is validated against its JSON Schema before it becomes a domain object. A
    malformed entry raises rather than degrading, because a corpus is authored by hand under
    deadline and a silent misread is worse than a loud stop.
"""

from __future__ import annotations

import json
from datetime import datetime
from functools import cached_property
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema import ValidationError as JsonSchemaValidationError

from aadesh_core.domain import (
    Citation,
    Entitlement,
    EntitlementAmount,
    InvocationLifecycle,
    InvokedStage,
    Obligation,
    SourceDocument,
    SourceState,
    StageBand,
)
from aadesh_core.errors import CorpusIntegrityError
from aadesh_core.verification import VerificationReport, verify_corpus

FORBIDDEN_KEYS = {"source_state", "verified", "is_verified"}

#: Schemas ship WITH THE CODE, not with the corpus. A corpus directory that supplied its own
#: schema could weaken its own validation -- the same self-certifying problem that
#: `_reject_self_declared_provenance` exists to prevent, one level up.
SCHEMA_DIR = Path(__import__("aadesh_core").__file__).parent / "corpus_schemas"


class LocalFileCorpus:
    """Reads corpus/ from the filesystem. No network, no AWS."""

    def __init__(self, root: Path, *, schema_dir: Path = SCHEMA_DIR) -> None:
        self.root = Path(root)
        self._schema_dir = Path(schema_dir)

    # -- verification -------------------------------------------------------

    @cached_property
    def _report(self) -> VerificationReport:
        return verify_corpus(self.root)

    def verification_report(self) -> VerificationReport:
        return self._report

    def _state_for(self, entry_id: str) -> SourceState:
        return (
            SourceState.VERIFIED
            if entry_id in self._report.verified_entry_ids
            else SourceState.UNSOURCED
        )

    # -- loading ------------------------------------------------------------

    def _read(self, relative: str, list_key: str) -> list[dict[str, Any]]:
        path = self.root / relative
        if not path.exists():
            return []
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise CorpusIntegrityError(f"{relative} is not valid JSON: {exc}") from exc
        entries = payload.get(list_key, [])
        for entry in entries:
            self._reject_self_declared_provenance(entry, relative)
        return entries

    @staticmethod
    def _reject_self_declared_provenance(entry: dict[str, Any], relative: str) -> None:
        reject_self_declared_provenance(entry, relative)

    def _validate(self, entry: dict[str, Any], schema_name: str) -> None:
        validate_entry(entry, schema_name, schema_dir=self._schema_dir)

    # -- RulesCorpus port ---------------------------------------------------

    def obligations(self) -> tuple[Obligation, ...]:
        out: list[Obligation] = []
        for entry in self._read("obligations/construction_site.json", "obligations"):
            self._validate(entry, "obligation.schema.json")
            out.append(
                Obligation(
                    obligation_id=entry["obligation_id"],
                    entity_types=tuple(entry["entity_types"]),
                    triggers_at_stage=entry["triggers_at_stage"],
                    label=entry["label"],
                    field=entry["field"],
                    operator=entry["operator"],
                    value=entry["value"],
                    citation=_citation(entry),
                    issues_parchi=entry["consequence"]["issues_parchi"],
                    worker_entitlement_ref=entry["consequence"].get("worker_entitlement_ref"),
                    source_state=self._state_for(entry["obligation_id"]),
                )
            )
        return tuple(out)

    def entitlements(self) -> tuple[Entitlement, ...]:
        out: list[Entitlement] = []
        for entry in self._read("entitlements/cess_fund.json", "entitlements"):
            self._validate(entry, "entitlement.schema.json")
            amount_entry = entry.get("amount")
            out.append(
                Entitlement(
                    entitlement_id=entry["entitlement_id"],
                    label=entry["label"],
                    citation=_citation(entry),
                    amount=(
                        None
                        if not amount_entry
                        else EntitlementAmount(
                            value_inr=amount_entry["value_inr"],
                            basis=amount_entry["basis"],
                            citation=_citation(amount_entry),
                        )
                    ),
                    readiness_requirements=tuple(
                        (r["label"], _citation(r)) for r in entry.get("readiness_requirements", [])
                    ),
                    source_state=self._state_for(entry["entitlement_id"]),
                )
            )
        return tuple(out)

    def stage_bands(self) -> tuple[StageBand, ...]:
        out: list[StageBand] = []
        for entry in self._read("stage_bands/grap_stage_bands.json", "stage_bands"):
            self._validate(entry, "stage_band.schema.json")
            out.append(
                StageBand(
                    stage=entry["stage"],
                    pollutant=entry["pollutant"],
                    aqi_lower=entry["aqi_lower"],
                    aqi_upper=entry.get("aqi_upper"),
                    citation=_citation(entry),
                    source_state=self._state_for(str(entry["stage"])),
                )
            )
        return tuple(out)

    # -- SourceDocumentStore port ------------------------------------------

    def documents(self) -> tuple[SourceDocument, ...]:
        path = self.root / "sources" / "manifest.json"
        if not path.exists():
            return ()
        manifest = json.loads(path.read_text(encoding="utf-8"))
        return tuple(
            SourceDocument(
                doc_id=d["doc_id"],
                title=d["title"],
                publisher=d["publisher"],
                source_url=d["source_url"],
                retrieved_at=datetime.fromisoformat(d["retrieved_at"]),
                sha256=d["sha256"],
                byte_size=d["byte_size"],
            )
            for d in manifest.get("documents", [])
        )

    def page_text(self, *, doc_id: str, page: int) -> str | None:
        manifest = {d["doc_id"]: d for d in self._manifest_documents()}
        doc = manifest.get(doc_id)
        if doc is None:
            return None
        page_file = self.root / doc["pages_dir"] / f"p{page}.txt"
        return page_file.read_text(encoding="utf-8") if page_file.exists() else None

    def _manifest_documents(self) -> list[dict[str, Any]]:
        path = self.root / "sources" / "manifest.json"
        if not path.exists():
            return []
        return json.loads(path.read_text(encoding="utf-8")).get("documents", [])

    # -- InvokedStageSource port -------------------------------------------

    def invoked_stage(self) -> InvokedStage | None:
        """The stage CURRENTLY in force, or None when none is.

        A revoked invocation is deliberately NOT returned here. It is evidence about the
        past, and handing it to the resolver would make January's Stage III keep enforcing in
        October -- the exact failure the lifecycle distinction exists to prevent. The replay
        record is available from `invocation_history()`.

        Raises when a stage IS recorded but its citation cannot be re-proved: an unprovable
        invoked stage is not degraded to "nothing applies", because that would silently drop
        every obligation in the corpus.
        """
        invocation = self._load_invocation()
        if invocation is None or not invocation.is_current:
            return None
        return invocation

    def invocation_history(self) -> tuple[InvokedStage, ...]:
        """Every invocation recorded, revoked ones included, for historical replay.

        This is what lets Aadesh say "Historical replay: CAQM invoked Stage III on 16 Jan
        2026" while `invoked_stage()` stays honestly empty.
        """
        invocation = self._load_invocation()
        return () if invocation is None else (invocation,)

    def _load_invocation(self) -> InvokedStage | None:
        """Parse invoked_stage.json into a domain object, proving it or raising."""
        path = self.root / "invoked_stage.json"
        if not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8")).get("invoked")
        if not payload:
            return None

        # `source_doc`, the same key every other citation in the corpus uses. The invoked
        # stage is a citation like any other, and giving it its own key name would make it
        # the one citation no generic check could find.
        doc_id = payload.get("source_doc")
        if not doc_id:
            raise CorpusIntegrityError(
                f"invoked_stage.json must name the order as 'source_doc' (found keys: "
                f"{sorted(payload)}). Every citation in this corpus names its document the "
                f"same way, so that verification can find all of them."
            )
        documents = {d["doc_id"]: d for d in self._manifest_documents()}
        if doc_id not in documents:
            raise CorpusIntegrityError(
                f"invoked_stage.json names order {doc_id!r}, which is not in the source "
                f"manifest. A stage invoked by an order nobody hashed cannot be cited."
            )

        # Shape first, so a malformed record fails with the field name; then the proof, which
        # is the check that actually protects the claim.
        validate_entry(payload, "invoked_stage.schema.json", schema_dir=self._schema_dir)

        if not self._invoked_stage_is_proved():
            raise CorpusIntegrityError(
                "invoked_stage.json invokes a stage that cannot be re-proved against its "
                "source. Either the citation is missing (source_doc, page and quote copied "
                "verbatim from that page), the quoted sentence does not name the stage it is "
                "cited for, or the document's bytes no longer hash to the manifest. Run "
                "`make verify` to see which. The invoked stage decides which obligations "
                "apply at all, so an unprovable one is refused rather than quietly applied."
            )

        try:
            invoked_at = datetime.fromisoformat(payload["invoked_at"])
        except ValueError as exc:
            raise CorpusIntegrityError(
                f"invoked_stage.json: invoked_at {payload['invoked_at']!r} is not an ISO-8601 "
                f"instant. Copy the date the order states, e.g. 2026-10-08T06:00:00+05:30."
            ) from exc

        lifecycle = InvocationLifecycle(payload.get("lifecycle", InvocationLifecycle.ACTIVE))
        revoked_at: datetime | None = None
        revocation_citation: Citation | None = None
        revocation = payload.get("revocation")
        if revocation is not None:
            try:
                revoked_at = datetime.fromisoformat(revocation["revoked_at"])
            except ValueError as exc:
                raise CorpusIntegrityError(
                    f"invoked_stage.json: revocation.revoked_at {revocation['revoked_at']!r} "
                    f"is not an ISO-8601 instant."
                ) from exc
            revocation_citation = Citation(
                source_doc=revocation["source_doc"],
                page=revocation["page"],
                quote=revocation["quote"],
            )

        return InvokedStage(
            stage=payload["stage"],
            order_doc_id=doc_id,
            order_sha256=documents[doc_id]["sha256"],
            invoked_at=invoked_at,
            lifecycle=lifecycle,
            revoked_at=revoked_at,
            revocation_citation=revocation_citation,
        )

    def _invoked_stage_is_proved(self) -> bool:
        """True only if EVERY citation the invocation carries re-proved.

        Now that an invocation can carry a revocation citation as well as its own, "any"
        would let a good revocation paper over a bad invocation. The stage is proved only when
        all of its citations are.
        """
        checks = [c for c in self._report.citations if c.entry_kind == "invoked_stage"]
        return bool(checks) and all(c.ok for c in checks)


def reject_self_declared_provenance(entry: dict[str, Any], where: str) -> None:
    """A corpus entry may not assert its own provenance.

    Shared with the ingestion CLI on purpose: if the writer and the loader disagreed here,
    an entry could be accepted on the way in and rejected on the way out -- or worse, the
    reverse.
    """
    present = FORBIDDEN_KEYS & entry.keys()
    if present:
        raise CorpusIntegrityError(
            f"{where}: entry declares {sorted(present)}. A corpus entry cannot assert "
            f"its own source_state -- verification against hashed source bytes is the "
            f"only thing that may set it. Remove the key."
        )


def validate_entry(
    entry: dict[str, Any], schema_name: str, *, schema_dir: Path = SCHEMA_DIR
) -> None:
    """Validate one corpus entry against a schema that ships with the CODE, not the corpus."""
    schema_path = Path(schema_dir) / schema_name
    if not schema_path.exists():
        raise CorpusIntegrityError(
            f"Schema {schema_name} is missing from {schema_dir}. Refusing to handle corpus "
            f"data unvalidated."
        )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    try:
        Draft202012Validator(schema).validate(entry)
    except JsonSchemaValidationError as exc:
        field = "/".join(str(p) for p in exc.absolute_path) or "<root>"
        raise CorpusIntegrityError(
            f"{schema_name}: invalid entry at {field}: {exc.message}"
        ) from exc


def _citation(entry: dict[str, Any]) -> Citation:
    return Citation(source_doc=entry["source_doc"], page=entry["page"], quote=entry["quote"])
