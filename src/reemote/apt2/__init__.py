"""Simulated apt facts and operations for the ``structure.py`` engine.

``facts`` mirrors pyinfra's apt facts (``AptPackages``, ``AptSources``,
``AptKeys``, ``SimulateOperationWillChange``) and simulates the read-only
``apt list --installed`` command; ``operations`` simulates the state-changing
``apt-get`` command.  Importing the submodules registers their command handlers
with :mod:`reemote.simulation`.
"""
