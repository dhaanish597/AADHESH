"""Which hosts count as an OFFICIAL source for the Aadesh corpus.

An obligation is only ever as strong as the document standing behind it, and a document
hosted on a mirror, a news site, or a well-meaning aggregator is not the order. The bytes
may even be identical -- but "identical to what, as verified by whom" is the whole question,
and a copy is not an answer.

So the corpus records the official domain a document was downloaded from, and ingestion
refuses anything else at the door. This is a *policy* list, not a legal fact: adding a host
here does not assert anything about law, only that this host is where the Commission
publishes. Keep it deliberately short.

The check lives in the core, not the CLI, so that a test can point at one definition. It has
no legal content and imports nothing heavy.
"""

from __future__ import annotations

from urllib.parse import urlparse

#: Hosts whose documents may enter the corpus. CAQM publishes orders and the GRAP schedule
#: on its own domain; the mirror is not the Commission.
OFFICIAL_SOURCE_HOSTS = frozenset({"caqm.nic.in"})


def source_host(url: str) -> str:
    """The lowercased hostname of `url`, or "" when it has none."""
    try:
        return (urlparse(url).hostname or "").lower()
    except ValueError:
        # urlparse raises on malformed IPv6-ish input; treat it as no host rather than
        # letting a bad URL take down the whole corpus load.
        return ""


def is_official_source_url(url: str) -> bool:
    """True only for an exact official host or a subdomain of one.

    ``caqm.nic.in`` and ``www.caqm.nic.in`` pass; ``caqm.nic.in.evil.example`` does not,
    because the match is on the host suffix and not on the string.
    """
    host = source_host(url)
    if not host:
        return False
    return any(
        host == official or host.endswith("." + official) for official in OFFICIAL_SOURCE_HOSTS
    )


def require_official_source_url(url: str) -> None:
    """Raise ``ValueError`` when `url` is not on an official domain. Callers wrap it."""
    if not is_official_source_url(url):
        raise ValueError(
            f"source URL {url!r} is not on an official domain "
            f"({', '.join(sorted(OFFICIAL_SOURCE_HOSTS))}). A mirror, a news article or a "
            f"saved copy is not the order. Download the document from the Commission itself."
        )
