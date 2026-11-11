"""Simulated apt state-changing commands ("operations").

The ``apt-get`` handler registers with :mod:`reemote.simulation` and mutates
the target host's package state -- the same ``state.packages`` that
``apt2.facts.apt list --installed`` renders.  That coupling is the point: after
``apt-get install cowsay`` the host's package set really contains ``cowsay``,
so a later ``apt list --installed`` in the same run differs from the one taken
before it, and the demo's ``check_changed`` Callback reports ``changed``.

Output mimics real ``apt-get``: the ``Reading package lists...`` preamble and
the ``N upgraded, N newly installed, N to remove and N not upgraded.`` summary
line that pyinfra's ``SimulateOperationWillChange`` fact parses.
"""
from __future__ import annotations

import shlex

from reemote.apt2.facts import installed_packages
from reemote.simulation import CompletedProcess, HostState, command

# Version assigned to a package installed without an explicit ``=version`` pin.
_DEFAULT_VERSION = "1.0-1"

_PREAMBLE = [
    "Reading package lists...",
    "Building dependency tree...",
    "Reading state information...",
]


def _summary(upgraded: int, installed: int, removed: int) -> str:
    """The ``apt-get`` closing summary line (pyinfra parses this exact shape)."""
    return f"{upgraded} upgraded, {installed} newly installed, {removed} to remove and 0 not upgraded."


@command("apt-get")
def apt_get(state: HostState, cmd: str) -> CompletedProcess:
    """Simulate ``apt-get``: dispatch on the sub-command.

    ``install`` / ``remove`` / ``purge`` mutate the host's package set;
    ``update`` refreshes the (simulated) package index; ``upgrade`` and
    friends report an up-to-date system.  Option flags (``-y``, ``-q``, ...)
    are ignored -- operands are the non-flag arguments.
    """
    argv = shlex.split(cmd)
    sub = argv[1] if len(argv) > 1 else ""
    operands = [a for a in argv[2:] if not a.startswith("-")]

    if sub == "install":
        return _install(state, cmd, operands)
    if sub in ("remove", "purge", "autoremove"):
        return _remove(state, cmd, operands)
    if sub == "update":
        return _update(cmd)
    if sub in ("upgrade", "dist-upgrade", "full-upgrade"):
        return _upgrade(cmd)
    return CompletedProcess(cmd, 0, 0, "", "")


def _install(state: HostState, cmd: str, operands: list[str]) -> CompletedProcess:
    """Add each not-yet-installed ``name[=version]`` operand to the host."""
    packages = installed_packages(state)
    newly: list[str] = []
    already: list[str] = []
    for spec in operands:
        name, _, version = spec.partition("=")
        if name in packages:
            already.append(name)
        else:
            packages[name] = {version or _DEFAULT_VERSION}
            newly.append(name)

    lines = list(_PREAMBLE)
    lines += [f"{name} is already the newest version." for name in already]
    if newly:
        lines.append("The following NEW packages will be installed:")
        lines.append("  " + " ".join(sorted(newly)))
    lines.append(_summary(0, len(newly), 0))
    return CompletedProcess(cmd, 0, 0, "\n".join(lines) + "\n", "")


def _remove(state: HostState, cmd: str, operands: list[str]) -> CompletedProcess:
    """Drop each installed operand from the host's package set."""
    packages = installed_packages(state)
    removed = [
        spec.partition("=")[0]
        for spec in operands
        if packages.pop(spec.partition("=")[0], None) is not None
    ]
    lines = list(_PREAMBLE)
    if removed:
        lines.append("The following packages will be REMOVED:")
        lines.append("  " + " ".join(sorted(removed)))
    lines.append(_summary(0, 0, len(removed)))
    return CompletedProcess(cmd, 0, 0, "\n".join(lines) + "\n", "")


def _update(cmd: str) -> CompletedProcess:
    """Refresh the package index; installs nothing, so state is unchanged."""
    out = (
        "Hit:1 http://deb.debian.org/debian bookworm InRelease\n"
        "Hit:2 http://deb.debian.org/debian bookworm-updates InRelease\n"
        "Hit:3 http://security.debian.org/debian-security bookworm-security InRelease\n"
        "Reading package lists...\n"
    )
    return CompletedProcess(cmd, 0, 0, out, "")


def _upgrade(cmd: str) -> CompletedProcess:
    """Report an up-to-date system (no version bumps are simulated)."""
    lines = list(_PREAMBLE)
    lines.append("0 upgraded, 0 newly installed, 0 to remove and 0 not upgraded.")
    return CompletedProcess(cmd, 0, 0, "\n".join(lines) + "\n", "")
