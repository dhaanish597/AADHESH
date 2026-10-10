"""The rules corpus, read from S3 and materialised to local disk before it is used.

Verification hashes the *bytes* of the source documents, so the corpus has to exist on a
filesystem to be re-proved at all. The adapter therefore does the only honest thing: it
downloads the objects once, to a local directory, and then hands that directory to the same
`LocalFileCorpus` loader the CLI and the local server use. Nothing about the loading or the
verification logic changes -- only where the bytes came from.

**The cache key is the S3 version id of `manifest.json`.** If the object has no version
(the bucket is versioned in the template, but a local emulator may not be), the ETag of the
manifest is used instead. A fresh materialisation happens only when that key changes, so a
warm Lambda container does not re-download 17 MB on every request -- while a redeployed
corpus is picked up because its manifest bytes changed.

A half-written tree is the failure mode this design is guarding against: the sync writes to a
scratch directory and renames it into place, so a crash mid-download leaves the previous,
complete tree rather than a truncated one that would report on bytes that are not in S3.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any, ClassVar

from aadesh_adapters.corpus.local_file import LocalFileCorpus

#: Directories of the corpus that are part of the deployed rules. `incoming_sources` holds the
#: raw downloads the hashed sources were derived from and is deliberately not deployed: the
#: evidence is `sources/`, and shipping the duplicates would double the download for nothing.
SYNC_ROOTS = (
    "sources/manifest.json",
    "invoked_stage.json",
    "obligations/",
    "stage_bands/",
    "entitlements/",
    "sources/",
)

DEFAULT_CACHE_ROOT = "/tmp/aadesh-corpus"


def _is_wanted(key: str) -> bool:
    return any(key == root or key.startswith(root) for root in SYNC_ROOTS)


class S3Corpus(LocalFileCorpus):
    """`RulesCorpus` + `SourceDocumentStore` + `InvokedStageSource`, backed by S3."""

    # Class-level on purpose: a warm Lambda container must not re-download a 17 MB corpus for
    # every invocation, and the cache key is the manifest's version id, so a redeploy still
    # invalidates it. ClassVar (rather than a plain attribute) is what says so to a reader.
    _synced: ClassVar[dict[tuple[str, str], str]] = {}

    def __init__(
        self,
        *,
        bucket: str,
        prefix: str = "corpus",
        cache_root: str | Path | None = None,
        s3: Any = None,
    ) -> None:
        if not bucket:
            from aadesh_core.errors import CorpusIntegrityError

            raise CorpusIntegrityError("S3Corpus requires a bucket name.")
        self._bucket = bucket
        self._prefix = prefix.strip("/") or "corpus"
        root = Path(cache_root or os.environ.get("AADESH_CORPUS_CACHE", DEFAULT_CACHE_ROOT))
        self._sync(bucket=self._bucket, prefix=self._prefix, root=root, s3=s3)
        super().__init__(root)

    # -- materialisation ----------------------------------------------------

    def _sync(self, *, bucket: str, prefix: str, root: Path, s3: Any) -> None:
        from aadesh_adapters.store.dynamo.client import s3_client

        client = s3 or s3_client()
        cache_key = (bucket, prefix)
        version = self._manifest_version(client, bucket, prefix)

        manifest_path = root / "sources" / "manifest.json"
        if (
            version is not None
            and self._synced.get(cache_key) == version
            and manifest_path.exists()
        ):
            return

        scratch = root.with_name(root.name + ".partial")
        if scratch.exists():
            shutil.rmtree(scratch, ignore_errors=True)
        scratch.mkdir(parents=True, exist_ok=True)
        try:
            paginator = client.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=bucket, Prefix=f"{prefix}/"):
                for obj in page.get("Contents", []):
                    key = obj["Key"]
                    relative = key[len(prefix) + 1 :]
                    if not relative or not _is_wanted(relative):
                        continue
                    destination = scratch / relative
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    client.download_file(bucket, key, str(destination))
            if not (scratch / "sources" / "manifest.json").exists():
                from aadesh_core.errors import CorpusIntegrityError

                raise CorpusIntegrityError(
                    f"s3://{bucket}/{prefix}/sources/manifest.json was not found, so there is "
                    f"no corpus to verify against. Upload the corpus before deploying."
                )
        except BaseException:
            shutil.rmtree(scratch, ignore_errors=True)
            raise

        if root.exists():
            shutil.rmtree(root, ignore_errors=True)
        scratch.rename(root)
        self._synced[cache_key] = version or "unknown"

    @staticmethod
    def _manifest_version(client: Any, bucket: str, prefix: str) -> str | None:
        """A key that changes when the corpus changes: version id, else ETag."""
        try:
            head = client.head_object(Bucket=bucket, Key=f"{prefix}/sources/manifest.json")
        except Exception as exc:
            from aadesh_core.errors import CorpusIntegrityError

            raise CorpusIntegrityError(
                f"s3://{bucket}/{prefix}/sources/manifest.json is not readable: {exc}"
            ) from exc
        return head.get("VersionId") or head.get("ETag")
