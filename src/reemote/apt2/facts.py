"""Simulated apt facts for the reemote ``apt2`` module.

Each function here mirrors the shape returned by a pyinfra apt fact
(``pyinfra/src/pyinfra/facts/apt.py``) so code written against those facts can
be exercised without a live host:

* ``apt_packages()``                   -> ``AptPackages``
* ``apt_sources()``                    -> ``AptSources``
* ``apt_keys()``                       -> ``AptKeys``
* ``simulate_operation_will_change()`` -> ``SimulateOperationWillChange``

The simulated data is realistic for a minimal Debian 12 (bookworm) server.

This module also provides the ``apt`` *command* simulation used by the
``structure.py`` engine (see :mod:`reemote.simulation`): ``apt list
--installed`` renders a host's current package state -- seeded from
``apt_packages()`` and mutated by ``apt-get`` in ``apt2.operations`` -- so the
pre-order traversal drives a realistic listing that reflects prior installs.
"""

from __future__ import annotations

import copy
import shlex
from dataclasses import dataclass
from typing import TypedDict

from reemote.simulation import CompletedProcess, HostState, command

# Matches pyinfra's ``facts.util.packaging.PackageVersionDict``:
# package name -> set of installed versions.
PackageVersionDict = dict[str, set[str]]


class AptSimulationDict(TypedDict):
    """Mirrors pyinfra's ``facts.apt.AptSimulationDict``.

    The parsed result of ``apt-get <command> --dry-run``: the four counts from
    the summary line ``"N upgraded, N newly installed, N to remove and N not
    upgraded."``
    """

    upgraded: int
    newly_installed: int
    removed: int
    not_upgraded: int


@dataclass(frozen=True)
class AptRepo:
    """One configured APT repository -- mirrors pyinfra's ``facts.apt.AptRepo``.

    A frozen dataclass that also exposes dict-like read access
    (``repo["type"]``, ``repo.get("url")``, ``"type" in repo``,
    ``repo.items()``, ``repo.to_json()``) for backward compatibility, exactly
    like the pyinfra original.  ``apt_sources()`` returns a ``list[AptRepo]``.
    """

    type: str  # "deb" or "deb-src"
    url: str  # repository URL
    distribution: str  # suite / distribution name (e.g. "bookworm")
    components: list[str]  # e.g. ["main", "contrib"]
    options: dict[str, str | list[str]]  # e.g. {"signed-by": "/etc/apt/keyrings/docker.gpg"}

    # --- dict-like interface (matches pyinfra.facts.apt.AptRepo) ---
    def __getitem__(self, key: str):
        return getattr(self, key)

    def __contains__(self, key: str) -> bool:
        return hasattr(self, key)

    def get(self, key: str, default=None):
        return getattr(self, key, default)

    def keys(self):
        return ["type", "url", "distribution", "components", "options"]

    def values(self):
        return [self.type, self.url, self.distribution, self.components, self.options]

    def items(self):
        return [(k, getattr(self, k)) for k in self.keys()]

    def __eq__(self, other) -> bool:
        # Enhanced equality that also works against plain dicts, matching
        # pyinfra's AptRepo.__eq__ (used by repo idempotency checks).
        if isinstance(other, dict):
            return all(getattr(self, k) == other.get(k) for k in self.keys())
        if isinstance(other, AptRepo):
            return self.items() == other.items()
        return False

    def to_json(self):
        return dict(self.items())


# A realistic installed-package set for a minimal Debian 12 (bookworm) server.
# Versions follow Debian conventions:
#   * optional epoch prefix      -- ``2:9.0.1378-1``, ``1:2.39.2-1.1``
#   * upstream version           -- ``5.2.15``, ``3.0.11``
#   * Debian revision            -- ``-1``, ``-2+b2`` (``+bN`` = binNMU)
#   * security / point-release   -- ``+deb12u1``, ``~deb12u2``
# Names carry no ``:arch`` suffix, which is what ``apt list --installed``
# reports on a single-architecture install.
_SIMULATED_PACKAGES: dict[str, str] = {
    "apt": "2.6.1",
    "base-files": "12.4+deb12u7",
    "base-passwd": "3.6.1",
    "bash": "5.2.15-2+b2",
    "bsdutils": "1:2.38.1-5+b1",
    "coreutils": "9.1-1",
    "curl": "7.88.1-10+deb12u1",
    "dash": "0.5.12-2",
    "debconf": "1.5.82",
    "debianutils": "5.7-0.4",
    "diffutils": "1:3.8-4",
    "dpkg": "1.21.22",
    "e2fsprogs": "1.47.0-2",
    "findutils": "4.9.0-4",
    "gcc-12-base": "12.2.0-14",
    "git": "1:2.39.2-1.1",
    "grep": "3.8-5",
    "gzip": "1.12-1",
    "hostname": "3.23+nmu1",
    "init-system-helpers": "1.65.2",
    "libc-bin": "2.36-9+deb12u3",
    "libc6": "2.36-9+deb12u3",
    "libssl3": "3.0.11-1~deb12u2",
    "login": "1:4.13+dfsg1-1+b1",
    "ncurses-base": "6.4-4",
    "openssh-server": "1:9.2p1-2+deb12u1",
    "openssl": "3.0.11-1~deb12u2",
    "python3": "3.11.2-1+b1",
    "sed": "4.9-1",
    "systemd": "252.17-1~deb12u1",
    "tar": "1.34+dfsg-1.2",
    "util-linux": "2.38.1-5+b1",
    "vim": "2:9.0.1378-1",
    "zlib1g": "1:1.2.13.dfsg-1",
}


def apt_packages() -> PackageVersionDict:
    """Return a simulated ``AptPackages`` fact.

    The return value matches pyinfra's ``AptPackages.process`` output exactly:
    a ``dict`` mapping each package name to a ``set`` of installed versions
    (``dict[str, set[str]]``).  An installed package normally has a single
    version, so every value is a one-element set -- the same shape
    ``parse_packages`` produces from ``apt list --installed``.

    Returns:
        A fresh ``dict[str, set[str]]`` on each call (mutating the result does
        not affect the module-level source data).
    """
    return {name: {version} for name, version in _SIMULATED_PACKAGES.items()}


# A realistic /etc/apt/sources.list for Debian 12 (bookworm): the three main
# archive suites plus a third-party (Docker) repo carrying a ``signed-by``
# option, exactly the shape ``AptSources.process`` parses into ``AptRepo``s.
_SIMULATED_SOURCES: list[AptRepo] = [
    AptRepo(
        type="deb",
        url="http://deb.debian.org/debian",
        distribution="bookworm",
        components=["main", "contrib", "non-free", "non-free-firmware"],
        options={},
    ),
    AptRepo(
        type="deb",
        url="http://deb.debian.org/debian",
        distribution="bookworm-updates",
        components=["main", "contrib", "non-free", "non-free-firmware"],
        options={},
    ),
    AptRepo(
        type="deb",
        url="http://security.debian.org/debian-security",
        distribution="bookworm-security",
        components=["main", "contrib", "non-free", "non-free-firmware"],
        options={},
    ),
    AptRepo(
        type="deb",
        url="https://download.docker.com/linux/debian",
        distribution="bookworm",
        components=["stable"],
        options={"signed-by": "/etc/apt/keyrings/docker.gpg"},
    ),
]


def apt_sources() -> list[AptRepo]:
    """Return a simulated ``AptSources`` fact.

    Matches pyinfra's ``AptSources.process`` output: a ``list[AptRepo]``, each
    ``AptRepo`` a frozen dataclass with dict-like access.  The list mirrors a
    stock Debian 12 (bookworm) ``sources.list`` plus one signed third-party
    repo.

    Returns:
        A deep copy on each call, so mutating a returned ``AptRepo``'s
        ``components``/``options`` cannot corrupt the module-level source data
        (pyinfra likewise re-parses fresh data on every fact fetch).
    """
    return copy.deepcopy(_SIMULATED_SOURCES)


# Realistic APT GPG keys as ``AptKeys`` reports them: a FLATTENED
# ``{key_id: details}`` dict (AptKeys.process merges every keyring's ``keys``).
# Each key_id is the low 16 hex chars of its 40-char fingerprint, ``length``
# is the RSA key size in bits, ``validity`` is a GPG trust code
# (``u`` = ultimate, ``f`` = full, ``-`` = unknown), and ``subkeys`` maps
# subkey id -> details (empty when the key has no subkeys).
_SIMULATED_KEYS: dict[str, dict] = {
    # Debian archive signing key (12/bookworm), with a signing subkey.
    "C4D5E6F708192A3B": {
        "validity": "u",
        "length": 4096,
        "subkeys": {
            "1A2B3C4D5E6F7080": {
                "validity": "u",
                "length": 4096,
                "fingerprint": "0F1E2D3C4B5A69788796A5B41A2B3C4D5E6F7080",
            },
        },
        "fingerprint": "8F1E4A2B3C5D6E7F8091A2B3C4D5E6F708192A3B",
        "uid_hash": "9E8D7C6B5A4938271605F4E3D2C1B0A9F8E7D6C5",
        "uid": "Debian Archive Automatic Signing Key (12/bookworm) <ftpmaster@debian.org>",
    },
    # Docker's release signing key, with a signing subkey.
    "8D81803C0EBFCD88": {
        "validity": "f",
        "length": 4096,
        "subkeys": {
            "7E3F2A1B9C8D7E6F": {
                "validity": "f",
                "length": 4096,
                "fingerprint": "A1B2C3D4E5F607182930A4B57E3F2A1B9C8D7E6F",
            },
        },
        "fingerprint": "9DC858229FC7DD38854AE2D88D81803C0EBFCD88",
        "uid_hash": "F93A8B2C1D4E5F60718293A4B5C6D7E8F9012345",
        "uid": "Docker Release (CE release signing) <release@docker.com>",
    },
    # Ubuntu archive signing key -- no subkeys (mirrors pyinfra's doc example).
    "3B4FE6ACC0B21F32": {
        "validity": "-",
        "length": 4096,
        "subkeys": {},
        "fingerprint": "790BC7277767219C42C86F933B4FE6ACC0B21F32",
        "uid_hash": "B7A02867A0C1D32B594B36C00E20C8C57E397748",
        "uid": "Ubuntu Archive Automatic Signing Key (2012) <ftpmaster@ubuntu.com>",
    },
}


def apt_keys() -> dict[str, dict]:
    """Return a simulated ``AptKeys`` fact.

    Matches pyinfra's ``AptKeys.process`` output: a FLATTENED
    ``dict[key_id, key_details]`` where each ``key_details`` has the keys
    ``validity``, ``length``, ``subkeys`` (itself a ``dict[subkey_id, dict]``),
    ``fingerprint``, ``uid_hash`` and ``uid``.

    Returns:
        A deep copy on each call, so mutating a returned key's nested
        ``subkeys`` dict cannot corrupt the module-level source data.
    """
    return copy.deepcopy(_SIMULATED_KEYS)


# Per-verb simulated dry-run counts for ``simulate_operation_will_change``.
_SIMULATED_CHANGES: dict[str, dict[str, int]] = {
    "install": {"newly_installed": 3},
    "remove": {"removed": 2},
    "purge": {"removed": 2},
    "autoremove": {"removed": 2},
    "upgrade": {"upgraded": 5, "not_upgraded": 1},
    "dist-upgrade": {"upgraded": 7, "not_upgraded": 1},
    "full-upgrade": {"upgraded": 7, "not_upgraded": 1},
}


def simulate_operation_will_change(command: str = "upgrade") -> AptSimulationDict:
    """Return a simulated ``SimulateOperationWillChange`` fact.

    Mirrors pyinfra's ``SimulateOperationWillChange``, which runs
    ``apt-get <command> --dry-run`` and parses the summary line
    ``"N upgraded, N newly installed, N to remove and N not upgraded."`` into
    an ``AptSimulationDict``.

    The ``command`` argument mirrors the parameterized pyinfra fact.  The
    simulation returns a representative, deterministic result derived from the
    command verb (``install`` / ``remove`` / ``upgrade`` / ``dist-upgrade``), so
    an install simulation differs from an upgrade one.  An unrecognised verb
    yields all-zero counts -- i.e. ``host.noop``, no changes would be made.
    """
    result: AptSimulationDict = {
        "upgraded": 0,
        "newly_installed": 0,
        "removed": 0,
        "not_upgraded": 0,
    }
    parts = command.split()
    verb = parts[0].lower() if parts else ""
    for key, value in _SIMULATED_CHANGES.get(verb, {}).items():
        result[key] = value
    return result


# ---------------------------------------------------------------------------
# Command simulation for the structure.py engine (see reemote.simulation)
# ---------------------------------------------------------------------------


def installed_packages(state: HostState) -> PackageVersionDict:
    """Return the host's installed-package set, seeding it on first access.

    The mutable per-host ``state.packages`` starts empty; the first apt command
    seeds it from the baseline :func:`apt_packages` simulation (which already
    returns a fresh copy, so later mutations cannot touch the module-level
    source data).  Both the ``apt list`` fact handler here and the ``apt-get``
    operation handler in ``apt2.operations`` go through this function, so an
    install becomes visible to a later listing on the same host within a run.
    """
    if not state.packages:
        state.packages = apt_packages()
    return state.packages


def render_apt_list_installed(packages: PackageVersionDict) -> str:
    """Render installed packages as ``apt list --installed`` stdout.

    Emits one line per (package, version) in the exact form pyinfra's
    ``AptPackages`` regex parses -- ``name/stable,now version arch
    [installed]`` -- sorted by name so the output is deterministic (the demo's
    change detection compares two such listings textually).  Real apt prints a
    ``Listing...`` banner to stderr; it is omitted here, matching how pyinfra
    runs ``apt list --installed 2>/dev/null``.
    """
    return "".join(
        f"{name}/stable,now {version} amd64 [installed]\n"
        for name in sorted(packages)
        for version in sorted(packages[name])
    )


@command("apt")
def apt(state: HostState, cmd: str) -> CompletedProcess:
    """Simulate the read-only ``apt`` front-end for the engine.

    Handles ``apt list --installed`` -- the query pyinfra's ``AptPackages``
    fact runs -- by rendering the host's current package state, so it reflects
    any earlier ``apt-get install`` in the same run.  Any other ``apt``
    sub-command succeeds with empty output (not separately simulated).
    """
    argv = shlex.split(cmd)
    sub = argv[1] if len(argv) > 1 else ""
    if sub == "list" and "--installed" in argv:
        out = render_apt_list_installed(installed_packages(state))
        return CompletedProcess(cmd, 0, 0, out, "")
    return CompletedProcess(cmd, 0, 0, "", "")
