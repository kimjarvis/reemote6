"""Simulated core system commands for the ``structure.py`` engine.

``facts`` simulates read-only commands (``uname``, ``whoami``, ``echo``);
``operations`` simulates state-changing ones (``touch``).  Importing the
submodules registers their handlers with :mod:`reemote.simulation`.
"""
