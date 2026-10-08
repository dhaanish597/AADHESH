"""Child process for `test_13b`: resolve an obligation with the model and network unavailable.

Run by the parent test with `sys.executable`. It blocks every AI SDK and every network client
at import time, then does the ordinary deterministic work -- load the corpus, resolve at the
invoked stage -- and prints a one-line verdict.

`urllib.parse` is deliberately NOT blocked: `aadesh_core.sources` parses source-document URLs
as data and dials nothing, so blocking the parser would be a false test rather than a strict
one. `socket` IS blocked, which is what "the network is down" actually means here.

Exit code 0 and a `RESOLVED` line mean the core produced a legal obligation with no model and
no network reachable. Anything else -- a blocked import on the real path, or a wrong answer --
makes the parent test fail.
"""

from __future__ import annotations

import importlib.abc
import sys

BLOCKED = {
    # models
    "openai",
    "anthropic",
    "litellm",
    "cohere",
    "mistralai",
    "ollama",
    "llama_cpp",
    "vllm",
    "transformers",
    "torch",
    "tensorflow",
    "langchain",
    "google",
    "vertexai",
    "bedrock",
    "strands",
    "sagemaker",
    "huggingface_hub",
    # the network
    "socket",
    "ssl",
    "http",
    "urllib3",
    "requests",
    "httpx",
    "aiohttp",
    "ftplib",
    "smtplib",
    "telnetlib",
    "xmlrpc",
    # AWS SDKs
    "boto3",
    "botocore",
}


class _Blocked(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in BLOCKED:
            raise ImportError(f"{fullname} is blocked: the model and network layer is unavailable")
        return None


sys.meta_path.insert(0, _Blocked())

# Fail loudly at import time if the block leaked -- a silently-imported socket would make the
# whole exercise meaningless.
for name in ("socket", "httpx", "boto3"):
    try:
        __import__(name)
    except ImportError:
        pass
    else:  # pragma: no cover
        raise SystemExit(f"the block did not take effect for {name}")


corpus_root = sys.argv[1]
sys.path[:0] = sys.argv[2:]

from datetime import UTC, datetime  # noqa: E402

from aadesh_adapters.corpus.local_file import LocalFileCorpus  # noqa: E402
from aadesh_core.domain import Provenance, SiteProfile, StationReading  # noqa: E402
from aadesh_core.resolver import resolve_obligations  # noqa: E402

NOW = datetime(2026, 10, 8, 12, 0, tzinfo=UTC)

result = resolve_obligations(
    site=SiteProfile(
        site_id="site-001",
        entity_type="construction_site",
        nearest_station_id="station-001",
        facts={"in_ncr": True, "activity_in_progress": False},
    ),
    corpus=LocalFileCorpus(corpus_root).snapshot(),
    now=NOW,
    reading=StationReading(
        station_id="station-001",
        parameter="AQI",
        value=420.0,
        observed_at=NOW,
        ingested_at=NOW,
        provenance=Provenance.MEASURED,
    ),
)

met = [r.obligation_id for r in result.results if r.status.value == "met"]
stage = result.stage.stage if result.stage else None
print(f"RESOLVED stage={stage} met={met}")
