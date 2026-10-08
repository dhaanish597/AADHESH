"""Prompt 8 — end-to-end verification and evidence integrity.

These tests are deliberately NOT unit tests. Each one drives the real production objects
(resolver, corpus loader, standing-order machine, parchi service, Cedar adapter) against the
real on-disk corpus, and asserts a property that must hold across the whole chain. Nothing
here is a fake of a component under test; the only fakes are the in-memory adapters the
project already ships for exactly this purpose.

They carry no `integration` marker on purpose: they need no Docker, no network and no AWS, so
they belong in the default gate (`make test` / `make check`). See docs/verification.md.
"""
