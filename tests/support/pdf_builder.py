"""Builds a minimal, valid, text-bearing PDF in memory.

Used so the ingestion tests exercise the REAL pypdf extraction path instead of mocking it.
A mocked extractor would prove the plumbing and nothing about whether a quote written by
hand can actually be found in the text pypdf produces -- which is the only thing that
matters for `make verify`.

The text content is obviously synthetic. Nothing here is, or pretends to be, law.
"""

from __future__ import annotations


def make_pdf(pages: list[str]) -> bytes:
    """A single-font PDF with one text line per page, laid out top-left."""
    objs: list[bytes] = []

    # 1 = catalog, 2 = page tree, then one page + one content stream per page, then the font.
    page_ids = [3 + 2 * i for i in range(len(pages))]
    font_id = 3 + 2 * len(pages)

    kids = b" ".join(b"%d 0 R" % pid for pid in page_ids)
    objs.append(b"<</Type/Catalog/Pages 2 0 R>>")
    objs.append(b"<</Type/Pages/Kids[" + kids + b"]/Count %d>>" % len(pages))

    for i, text in enumerate(pages):
        content_id = page_ids[i] + 1
        escaped = text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")
        stream = b"BT /F1 11 Tf 20 160 Td (" + escaped.encode("latin-1", "replace") + b") Tj ET"
        objs.append(
            b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 500 200]/Contents %d 0 R"
            b"/Resources<</Font<</F1 %d 0 R>>>>>>" % (content_id, font_id)
        )
        objs.append(b"<</Length %d>>stream\n" % len(stream) + stream + b"\nendstream")

    objs.append(b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>")

    out = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    for i, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj" % i + body + b"endobj\n"

    xref_at = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    out += b"trailer<</Size %d/Root 1 0 R>>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objs) + 1,
        xref_at,
    )
    return bytes(out)
