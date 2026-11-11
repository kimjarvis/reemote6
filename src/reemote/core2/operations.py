"""Simulated state-changing system commands ("operations").

These handlers register with :mod:`reemote.simulation` and *mutate* the target
host's ``HostState``, mirroring pyinfra's operations.  ``touch`` records the
paths it creates so the simulation is honest about what an operation changed;
the engine reports ``changed`` for a successful PUT regardless (see
``run_operation``), which is what the demo's ``mark`` leaf asserts.
"""
from __future__ import annotations

import shlex

from reemote.simulation import CompletedProcess, HostState, command


@command("touch")
def touch(state: HostState, cmd: str) -> CompletedProcess:
    """Simulate ``touch``: create/update files, recording their paths.

    Option flags (``-a``, ``-m``, ``--no-create``, ...) are skipped; every
    remaining operand is treated as a path and added to the host's file set.
    ``touch`` writes nothing to stdout and exits 0 on success.
    """
    for operand in shlex.split(cmd)[1:]:
        if not operand.startswith("-"):
            state.files.add(operand)
    return CompletedProcess(cmd, 0, 0, "", "")
