# Corpus — rules as data, with provenance

**Every file in this directory is intentionally empty.** That is the correct Day 1 state and
`make verify` exits non-zero because of it.

## The rule that governs this directory

> Do not encode GRAP thresholds, action lists, or entitlement amounts from memory, from a
> strategy document, or from a news article.

GRAP has been revised repeatedly, with orders amending earlier orders. For every measure you
intend to encode, you must locate the **current** CAQM order, download it from the official
domain, hash the bytes, and encode only from the text you are holding.

**If you cannot establish which order is current for a measure, drop that measure.** Ten certain
obligations beat twenty-five uncertain ones. A confidently wrong citation is worse than no
citation, because provenance has been loudly advertised.

## Layout

```
corpus/
├── schemas/                      JSON Schemas. Data that fails validation cannot load.
├── sources/
│   ├── manifest.json             Provenance: doc_id, sha256, official URL, retrieved_at
│   ├── <doc_id>.pdf              The EXACT downloaded bytes. Committed on purpose: it is
│   │                             what makes `make verify` reproducible for a judge.
│   └── pages/<doc_id>/p<N>.txt   Extracted per-page text. Quotes are checked against these.
├── obligations/construction_site.json
├── entitlements/cess_fund.json
├── stage_bands/grap_stage_bands.json   AQI→stage thresholds. THE ONLY place they may exist.
└── invoked_stage.json            Which stage a CAQM ORDER has invoked (not computed from AQI).
```

## Adding a document

1. Locate the current order on the official CAQM domain. Not a mirror, not a news PDF.
2. Download it and move it to `corpus/sources/<doc_id>.pdf`.
3. Compute the hash and add a `documents[]` entry to `sources/manifest.json`:
   ```bash
   sha256sum corpus/sources/<doc_id>.pdf
   ```
4. Extract page text to `corpus/sources/pages/<doc_id>/p<N>.txt`, one file per page, 1-indexed.
5. Add obligations / entitlements / stage bands quoting **verbatim** from those page files.
6. Run `make verify`. If a quote does not appear byte-for-byte on the page it claims, it fails.

## Why `quote` must be verbatim

`make verify` re-reads the extracted page text and asserts the `quote` string appears in it.
A paraphrase — however faithful — fails. This is deliberate: it is the mechanism that stops
good intentions from degrading into remembered law under deadline pressure.

## Two concepts that are never conflated

- **Invoked stage** — set by a CAQM *order*. Carries the order's `doc_id` and `sha256`.
- **Implied stage** — derived from a station reading via the cited `stage_bands`.

A stage is invoked by an order, not computed by arithmetic. CAQM can invoke pre-emptively on a
forecast, or hold off. When invoked and implied diverge, Aadesh says so explicitly rather than
quietly preferring one.

Until `stage_bands` is populated from a hashed source, the implied stage is `UNKNOWN`.

## Amounts

`entitlement.amount` is `null` unless a specific figure appears in a hashed source document,
and the figure carries its own independent citation. When it is null, Aadesh reports **displaced
worker-days**, which is always provable. Never populate an amount to make a demo number look
better.
