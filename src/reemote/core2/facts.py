"""Simulated read-only system commands ("facts") for the structure.py engine.

These handlers register with :mod:`reemote.simulation` and produce realistic
output for the informational commands the demo tree describes -- ``uname``,
``whoami`` and ``echo`` -- mirroring pyinfra's server facts.  Each handler
receives the target host's ``HostState`` and the full command string, and
returns a ``CompletedProcess``; because they only *read* state they never
mutate it.

``uname`` output is host-specific: the nodename field is the simulated host's
name, so ``uname -a`` differs per host just as it would on real machines.
"""
from __future__ import annotations

import shlex

from reemote.simulation import CompletedProcess, HostState, command

# A Debian 12 (bookworm) kernel, matching the package data in apt2.facts.
_RELEASE = "6.1.0-13-amd64"
_VERSION = "#1 SMP PREEMPT_DYNAMIC Debian 6.1.58-1 (2023-10-04)"
_MACHINE = "x86_64"


@command("uname")
def uname(state: HostState, cmd: str) -> CompletedProcess:
    """Simulate ``uname``: print system information.

    Supports the common flags; ``-a`` (and no flag) prints the full banner
    with this host's name as the nodename, ``-s`` the kernel name, ``-n`` the
    nodename, ``-r`` the release and ``-m`` the machine hardware name.
    """
    args = shlex.split(cmd)[1:]
    kernel = state.kernel
    nodename = state.name
    if not args or "-a" in args:
        out = (
            f"{kernel} {nodename} {_RELEASE} {_VERSION} {_MACHINE} GNU/Linux\n"
        )
    elif "-s" in args:
        out = f"{kernel}\n"
    elif "-n" in args:
        out = f"{nodename}\n"
    elif "-r" in args:
        out = f"{_RELEASE}\n"
    elif "-m" in args:
        out = f"{_MACHINE}\n"
    elif "-o" in args:
        out = "GNU/Linux\n"
    else:
        out = f"{kernel}\n"
    return CompletedProcess(cmd, 0, 0, out, "")


@command("whoami")
def whoami(state: HostState, cmd: str) -> CompletedProcess:
    """Simulate ``whoami``: print the effective user (the simulation is root)."""
    return CompletedProcess(cmd, 0, 0, f"{state.user}\n", "")


@command("echo")
def echo(state: HostState, cmd: str) -> CompletedProcess:
    """Simulate ``echo``: print its arguments, separated by single spaces."""
    args = shlex.split(cmd)[1:]
    return CompletedProcess(cmd, 0, 0, " ".join(args) + "\n", "")
