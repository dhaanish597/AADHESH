"""INVARIANT: any port module can be imported on its own, before anything else.

A port is the first thing an adapter author imports -- they open `ports/parchi_ack.py` to see
what they have to implement, and they import exactly that module. So if a port only imports
successfully as a side effect of some other module having been loaded first, the boundary is
fragile in the one place it is most likely to be touched, and it fails for the person least
able to diagnose it.

This is checked in a fresh interpreter per module, because the failure it guards against is
invisible in a process where the import order happened to be favourable -- which is exactly
how it survives a normal test run.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PORTS = ROOT / "services" / "aadesh_core" / "ports"

PORT_MODULES = sorted(
    f"aadesh_core.ports.{p.stem}" for p in PORTS.glob("*.py") if p.stem != "__init__"
)


def test_there_are_ports_to_check():
    """A glob that matches nothing would make every test below vacuously pass."""
    assert PORT_MODULES, f"no port modules found under {PORTS}"


@pytest.mark.parametrize("module", PORT_MODULES)
def test_a_port_imports_first_in_a_fresh_interpreter(module):
    result = subprocess.run(
        [sys.executable, "-c", f"import {module}"],
        capture_output=True,
        text=True,
        cwd=ROOT,
        env={"PYTHONPATH": str(ROOT / "services"), "PATH": ""},
    )

    assert result.returncode == 0, (
        f"`import {module}` fails when it is the first import in a fresh process, so the port "
        f"cannot be reached except by luck of import order.\n{result.stderr}"
    )
