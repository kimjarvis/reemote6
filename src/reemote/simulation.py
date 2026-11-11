"""Simulated shell-command execution for the ``structure.py`` engine.

In ``structure.py`` a ``Shell`` leaf only *describes* a command; it is never
really run.  The engine's ``run_operation`` delegates every such command here,
which turns the description into a realistic simulated ``CompletedProcess``.
The pre-order traversal therefore drives *actual* (simulated) commands and the
command tree processes *actual* (simulated) responses.

Dispatch is by program name (``argv[0]``).  Handlers live beside the domain
they simulate and register themselves with the ``@command`` decorator:

* ``core2.facts``      -- read-only system commands (``uname``, ``whoami``,
                          ``echo``);
* ``core2.operations`` -- state-changing system commands (``touch``);
* ``apt2.facts``       -- ``apt list --installed`` (reads the package state);
* ``apt2.operations``  -- ``apt-get install/update/upgrade/remove`` (mutates
                          the package state).

Each handler receives the target host's mutable ``HostState`` and the command
string, and returns a ``CompletedProcess``.  Because the state is mutable and
keyed per host, ``apt-get install cowsay`` actually adds ``cowsay`` to that
host's package set, so a later ``apt list --installed`` reflects the change --
which the demo's ``check_changed`` Callback detects.

State is per host and per run: ``execute()`` calls ``reset()`` so each run
starts from the simulated baseline (no leakage between runs).  The engine is
single-threaded ``asyncio``, so the module-level state and registry are safe.

``load_handlers()`` imports the handler modules lazily (inside the function,
not at module scope) to avoid a circular import: the handler modules import
this one for ``command`` / ``HostState`` / ``CompletedProcess``.
"""
from __future__ import annotations

import logging
import shlex
from dataclasses import dataclass, field
from typing import Callable, Dict, Set


# ---------------------------------------------------------------------------
# Simulated stand-in for asyncssh.SSHCompletedProcess
# ---------------------------------------------------------------------------


@dataclass
class CompletedProcess:
    """Stand-in for ``asyncssh.SSHCompletedProcess``.

    Returned by every command handler and adapted to a plain dict by
    ``structure.completed_process_to_dict`` (the ADAPTER pattern).
    """

    command: str
    exit_status: int
    returncode: int
    stdout: str
    stderr: str


# ---------------------------------------------------------------------------
# Per-host simulated state
# ---------------------------------------------------------------------------


@dataclass
class HostState:
    """Mutable state of ONE simulated host, persisted across a run's rounds.

    ``packages`` is the apt installed-package database (``name -> versions``);
    it is seeded lazily from ``apt2.facts`` on first apt access so that this
    module need not import apt2 at load time.  ``files`` tracks paths created
    by ``touch``.  ``user`` / ``kernel`` back ``whoami`` and ``uname``.
    """

    name: str
    packages: Dict[str, Set[str]] = field(default_factory=dict)
    files: Set[str] = field(default_factory=set)
    user: str = "root"
    kernel: str = "Linux"


# A handler turns (host state, command string) into a CompletedProcess.
Handler = Callable[[HostState, str], CompletedProcess]

# program name (argv[0]) -> handler
_HANDLERS: Dict[str, Handler] = {}

# host name -> mutable state for the current run
_STATES: Dict[str, HostState] = {}


# ---------------------------------------------------------------------------
# Handler registration
# ---------------------------------------------------------------------------


def register(program: str, handler: Handler) -> None:
    """Register ``handler`` as the simulator for commands whose ``argv[0]`` is
    ``program`` (e.g. ``"uname"``, ``"apt-get"``)."""
    _HANDLERS[program] = handler


def command(program: str) -> Callable[[Handler], Handler]:
    """Decorator form of :func:`register` -- binds a handler to a program name.

    Used by the ``core2`` / ``apt2`` handler modules so each command's
    simulation lives beside its domain::

        @command("uname")
        def uname(state: HostState, cmd: str) -> CompletedProcess: ...
    """

    def decorator(fn: Handler) -> Handler:
        register(program, fn)
        return fn

    return decorator


def load_handlers() -> None:
    """Import the handler modules once, triggering their ``@command``
    registration.

    Imported lazily (inside the function) because those modules import this
    one at their module scope; importing them here at runtime -- after this
    module has fully loaded -- avoids a circular import.
    """
    global _HANDLERS_LOADED
    if _HANDLERS_LOADED:
        return
    _HANDLERS_LOADED = True
    # Side-effect imports: each module registers its handlers via @command.
    import reemote.apt2.facts  # noqa: F401
    import reemote.apt2.operations  # noqa: F401
    import reemote.core2.facts  # noqa: F401
    import reemote.core2.operations  # noqa: F401


_HANDLERS_LOADED = False


# ---------------------------------------------------------------------------
# State management
# ---------------------------------------------------------------------------


def state_for(host_name: str) -> HostState:
    """Return the mutable ``HostState`` for ``host_name``, creating it on first
    use within the current run."""
    state = _STATES.get(host_name)
    if state is None:
        state = HostState(name=host_name)
        _STATES[host_name] = state
    return state


def reset() -> None:
    """Drop all per-host simulated state.

    Called by ``structure.execute()`` at the start of each run so every run
    begins from the simulated baseline (packages re-seed lazily from
    ``apt2.facts``); without it, a package installed in one run would leak
    into the next.
    """
    _STATES.clear()


# ---------------------------------------------------------------------------
# Command execution
# ---------------------------------------------------------------------------


def run_command(host_name: str, command: str) -> CompletedProcess:
    """Simulate running ``command`` on host ``host_name``.

    Mirrors what reemote's SSH layer would return for a remote command:
      * ``ssh-error`` raises, reproducing a connection failure the engine
        catches and records (the "catch and record" pattern);
      * any command containing ``fail`` exits non-zero;
      * a leading ``sudo`` is stripped, then the command is dispatched to the
        handler registered for its program name (``argv[0]``);
      * an unhandled program logs a warning and succeeds with empty output, so
        an unexpected command never crashes a run.
    """
    load_handlers()
    state = state_for(host_name)

    # Demonstration hooks preserved from the original inline simulation.
    if command == "ssh-error":
        raise RuntimeError("Simulated SSH connection error")
    if "fail" in command:
        return CompletedProcess(command, 1, 1, "", "simulated failure")

    # `sudo cmd ...` runs `cmd ...` as root; the simulation is already root, so
    # drop the prefix.  Pass the handler the effective (sudo-stripped) command
    # so it parses argv[1] as the sub-command; keep the original string when
    # there was no sudo, so CompletedProcess.command matches the input exactly.
    argv = shlex.split(command)
    if argv and argv[0] == "sudo":
        argv = argv[1:]
        effective = shlex.join(argv)
    else:
        effective = command
    program = argv[0] if argv else ""

    handler = _HANDLERS.get(program)
    if handler is None:
        logging.warning(
            "simulation: no handler for program %r (command %r)", program, command
        )
        return CompletedProcess(command, 0, 0, "", "")
    return handler(state, effective)
