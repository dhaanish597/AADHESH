"""Builds throwaway corpora on disk for verification tests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


class CorpusBuilder:
    """Writes a corpus tree. Defaults produce an EMPTY but structurally valid corpus."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self._documents: list[dict] = []
        self._obligations: list[dict] = []
        self._entitlements: list[dict] = []
        self._stage_bands: list[dict] = []
        self._pages: dict[tuple[str, int], str] = {}

    def with_document(
        self,
        *,
        doc_id: str = "test-order",
        body: bytes = b"%PDF-1.4 fake bytes for a source document",
        sha256: str | None = None,
    ) -> CorpusBuilder:
        """Add a source document. Pass `sha256` explicitly to simulate a hash mismatch."""
        self._documents.append(
            {
                "doc_id": doc_id,
                "title": "Test order",
                "publisher": "Test Authority",
                "source_url": "https://example.invalid/test-order.pdf",
                "retrieved_at": "2026-10-08T09:00:00+00:00",
                "sha256": sha256 or hashlib.sha256(body).hexdigest(),
                "byte_size": len(body),
                "local_path": f"sources/{doc_id}.pdf",
                "pages_dir": f"sources/pages/{doc_id}",
                "_body": body,
            }
        )
        return self

    def with_page(self, *, doc_id: str = "test-order", page: int = 4, text: str) -> CorpusBuilder:
        self._pages[(doc_id, page)] = text
        return self

    def with_obligation(
        self,
        *,
        obligation_id: str = "test-ob-01",
        doc_id: str = "test-order",
        page: int = 4,
        quote: str,
    ) -> CorpusBuilder:
        self._obligations.append(
            {
                "obligation_id": obligation_id,
                "entity_types": ["construction_site"],
                "triggers_at_stage": 3,
                "label": "Test obligation",
                "field": "has_dust_generating_activity",
                "operator": "eq",
                "value": True,
                "source_doc": doc_id,
                "page": page,
                "quote": quote,
                "consequence": {"issues_parchi": True},
            }
        )
        return self

    def with_entitlement(
        self,
        *,
        entitlement_id: str = "test-ent-01",
        doc_id: str = "test-order",
        page: int = 4,
        quote: str,
    ) -> CorpusBuilder:
        self._entitlements.append(
            {
                "entitlement_id": entitlement_id,
                "label": "Test entitlement",
                "source_doc": doc_id,
                "page": page,
                "quote": quote,
                "amount": None,
                "readiness_requirements": [],
            }
        )
        return self

    def build(self) -> Path:
        corpus = self.root
        (corpus / "sources" / "pages").mkdir(parents=True, exist_ok=True)
        (corpus / "obligations").mkdir(parents=True, exist_ok=True)
        (corpus / "entitlements").mkdir(parents=True, exist_ok=True)
        (corpus / "stage_bands").mkdir(parents=True, exist_ok=True)

        manifest_docs = []
        for doc in self._documents:
            body = doc.pop("_body")
            (corpus / doc["local_path"]).write_bytes(body)
            (corpus / doc["pages_dir"]).mkdir(parents=True, exist_ok=True)
            manifest_docs.append(doc)

        for (doc_id, page), text in self._pages.items():
            page_file = corpus / "sources" / "pages" / doc_id / f"p{page}.txt"
            page_file.parent.mkdir(parents=True, exist_ok=True)
            page_file.write_text(text, encoding="utf-8")

        _write(corpus / "sources" / "manifest.json", {"documents": manifest_docs})
        _write(
            corpus / "obligations" / "construction_site.json", {"obligations": self._obligations}
        )
        _write(corpus / "entitlements" / "cess_fund.json", {"entitlements": self._entitlements})
        _write(corpus / "stage_bands" / "grap_stage_bands.json", {"stage_bands": self._stage_bands})
        return corpus


def _write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
