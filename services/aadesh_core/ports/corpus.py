"""Corpus ports: the rules as data, and the documents that justify them.

Split into three because they answer genuinely different questions, and conflating them is
how a system ends up trusting a file's own claim about itself:

  * `RulesCorpus`         -- what obligations, entitlements and stage bands exist
  * `SourceDocumentStore` -- the exact bytes and extracted page text being cited
  * `InvokedStageSource`  -- which stage a CAQM ORDER has invoked

An implementation of `RulesCorpus` MUST derive `source_state` from a verification run against
the source documents. It must never read it from the data file: a corpus cannot assert its
own provenance.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from aadesh_core.domain import Entitlement, InvokedStage, Obligation, SourceDocument, StageBand
from aadesh_core.verification import VerificationReport


@runtime_checkable
class RulesCorpus(Protocol):
    def obligations(self) -> tuple[Obligation, ...]: ...
    def entitlements(self) -> tuple[Entitlement, ...]: ...
    def stage_bands(self) -> tuple[StageBand, ...]: ...
    def verification_report(self) -> VerificationReport: ...


@runtime_checkable
class SourceDocumentStore(Protocol):
    def documents(self) -> tuple[SourceDocument, ...]: ...
    def page_text(self, *, doc_id: str, page: int) -> str | None: ...


@runtime_checkable
class InvokedStageSource(Protocol):
    def invoked_stage(self) -> InvokedStage | None:
        """The stage CURRENTLY in force, or None if none is.

        None means "no order in the corpus invokes a stage" (or the only invocation on record
        has been revoked). The resolver treats that as UNKNOWN rather than as "nothing
        applies". A revoked invocation is never returned here.
        """
        ...

    def invocation_history(self) -> tuple[InvokedStage, ...]:
        """Every invocation on record, revoked ones included, for historical replay.

        This is deliberately separate from `invoked_stage()`: keeping them apart is what makes
        it impossible to confuse "the stage CAQM invoked last January" with "the stage in
        force now".
        """
        ...
