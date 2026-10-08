"""Static guard: no legal facts may be hardcoded in the deterministic core.

Aadesh's whole credibility claim is that every enforcement-relevant fact traces back to a
hashed, cited source document. Two kinds of fact are especially tempting to inline under
deadline pressure, and both would quietly destroy that claim:

  * **GRAP stage thresholds** -- the AQI bands that map a reading to a stage. These live in
    the CAQM order, so they belong in corpus/stage_bands/, cited. `if aqi > 400` is the
    single most likely shortcut at 2 AM on Saturday.
  * **Rupee entitlement amounts** -- a figure nobody can cite, hardcoded to make a demo
    counter look better.

This scanner is deliberately a blunt instrument. It is proven able to fail by
tests/unit/test_source_scan_guard.py, which feeds it sources that are in breach.

Test-support code: imported only by tests, never by production.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

#: Detection window for integer literals, NOT a statement about law. Any integer in this
#: range inside the domain or resolver is suspicious enough to require either a citation in
#: the corpus or an explicit suppression comment. Values outside it (durations, counts,
#: byte sizes) are left alone.
SCAN_WINDOW_LOW = 101
SCAN_WINDOW_HIGH = 1000

#: An explicit, reviewable opt-out. Grep-able in review.
SUPPRESSION_MARKER = "noqa: aadesh-no-legal-literal"

#: Identifier fragments that mean "this holds money".
_MONEY_NAME_RE = re.compile(
    r"AMOUNT|RUPEE|INR|COMPENSATION|WAGE|PAYOUT|MONEY|SALARY|STIPEND|CESS_VALUE",
    re.IGNORECASE,
)

#: Currency symbols only. "INR" is excluded here on purpose: it appears legitimately in
#: identifiers like `value_inr`, and the money-constant rule already covers those.
_CURRENCY_RE = re.compile(r"[₹₨]|\bRs\.")


@dataclass(frozen=True)
class Violation:
    kind: str
    path: str
    line: int
    detail: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: [{self.kind}] {self.detail}"


def _suppressed_lines(source: str) -> set[int]:
    return {i for i, line in enumerate(source.splitlines(), start=1) if SUPPRESSION_MARKER in line}


def _numeric_literals(tree: ast.AST, path: str) -> Iterator[Violation]:
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant):
            continue
        # bool is a subclass of int; True/False are never thresholds.
        if isinstance(node.value, bool) or not isinstance(node.value, int | float):
            continue
        if SCAN_WINDOW_LOW <= node.value <= SCAN_WINDOW_HIGH:
            yield Violation(
                kind="numeric-literal",
                path=path,
                line=node.lineno,
                detail=(
                    f"integer literal {node.value} falls in the AQI-band scan window "
                    f"[{SCAN_WINDOW_LOW}, {SCAN_WINDOW_HIGH}]. GRAP thresholds belong in "
                    f"corpus/stage_bands/ with a citation, not in code."
                ),
            )


def _money_constants(tree: ast.AST, path: str) -> Iterator[Violation]:
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            targets = node.targets
            value = node.value
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
            value = node.value
        else:
            continue

        if value is None or not isinstance(value, ast.Constant):
            continue
        if isinstance(value.value, bool) or not isinstance(value.value, int | float):
            continue

        for target in targets:
            name = getattr(target, "id", None) or getattr(target, "attr", None)
            if name and _MONEY_NAME_RE.search(name):
                yield Violation(
                    kind="money-constant",
                    path=path,
                    line=node.lineno,
                    detail=(
                        f"{name} = {value.value} looks like a hardcoded monetary amount. "
                        f"Entitlement amounts are optional and citation-backed; see "
                        f"corpus/schemas/entitlement.schema.json."
                    ),
                )


def _currency_symbols(source: str, path: str) -> Iterator[Violation]:
    for i, line in enumerate(source.splitlines(), start=1):
        match = _CURRENCY_RE.search(line)
        if match:
            yield Violation(
                kind="currency-symbol",
                path=path,
                line=i,
                detail=(
                    f"currency symbol {match.group(0)!r} in the deterministic core. "
                    f"Rendering money is a presentation concern and the figure must come "
                    f"from a cited entitlement amount."
                ),
            )


def scan_source(source: str, *, path: str = "<string>") -> list[Violation]:
    """Scan one Python source string. Returns violations sorted by line."""
    tree = ast.parse(source)
    suppressed = _suppressed_lines(source)
    found = [
        *_numeric_literals(tree, path),
        *_money_constants(tree, path),
        *_currency_symbols(source, path),
    ]
    return sorted(
        (v for v in found if v.line not in suppressed),
        key=lambda v: (v.line, v.kind),
    )


def scan_file(path: Path, *, display_path: str | None = None) -> list[Violation]:
    return scan_source(
        path.read_text(encoding="utf-8"),
        path=display_path or path.as_posix(),
    )


def scan_tree(root: Path, *, relative_to: Path | None = None) -> list[Violation]:
    """Scan every .py file under `root`, recursively."""
    violations: list[Violation] = []
    base = relative_to or root
    for py in sorted(root.rglob("*.py")):
        violations.extend(scan_file(py, display_path=py.relative_to(base).as_posix()))
    return violations
