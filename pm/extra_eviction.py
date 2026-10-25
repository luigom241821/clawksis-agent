"""Keep an update alive when a recorded opt-in extra no longer builds on the new core.

Same contract as plugin eviction (pm.plugin_eviction): an update has nobody to ask and
must not fail because of an optional feature. Core can move under an extra that built
before, e.g. a newer Python for which a dependency ships no wheel and the machine has no
compiler (python-olm under ``matrix`` on Python 3.14). When the build of the recorded
selection fails and uv names the extra that pulled the failing package in
(``hint: `pkg` (v1) was included because `project[extra]` ...``), that extra leaves the
selection with a notice and the update continues. Only extras uv names are dropped, never
``all``; any other failure still fails. Every extra on this path was carried over (the
recorded selection, a main-era venv's inventory, configured features): a deliberate
``clawk pm install --extra X`` does not evict, so its failure still reaches the user.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable

from pm.environment import BuildFailure

_INCLUDED_BY = re.compile(
    r"`(?P<package>[^`\s]+)`(?: \(v[^)]*\))? was included because "
    r"`(?P<project>[A-Za-z0-9_.-]+)\[(?P<extras>[A-Za-z0-9_.,-]+)\]`"
)


def _normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def blamed_extras(output: str, project: str) -> dict[str, str]:
    """``{extra: failing package}`` for the extras of *project* that uv's hints blame."""
    blamed: dict[str, str] = {}
    for match in _INCLUDED_BY.finditer(output):
        if _normalize(match["project"]) != _normalize(project):
            continue
        for extra in match["extras"].split(","):
            blamed.setdefault(extra.strip(), match["package"])
    return blamed


def commit_dropping_extras(
    commit: Callable[[], None],
    *,
    project: str,
    recorded: Iterable[str],
    dropped: dict[str, str],
) -> None:
    """Run *commit*; while its build fails on a carried extra uv blames, drop it and retry.

    *dropped* is shared with *commit*, which builds the selection minus it.
    """
    recorded = set(recorded)
    while True:
        try:
            commit()
            return
        except BuildFailure as failure:
            blamed = blamed_extras(failure.output or failure.cause, project)
            new = {
                extra: package
                for extra, package in blamed.items()
                if extra in recorded and extra != "all" and extra not in dropped
            }
            if not new:
                raise
            dropped.update(new)


def without_dropped(fact: dict, dropped: dict[str, str], shipped) -> dict:
    """*fact* with the dropped extras taken out of its recorded selection."""
    if not dropped:
        return fact
    extras = fact.get("extras", shipped or [])
    return {**fact, "extras": [e for e in extras if e not in dropped]}


def kept(extras, dropped: dict[str, str]) -> list[str] | None:
    """The carried *extras* minus the dropped ones (None stays None)."""
    return None if extras is None else [e for e in extras if e not in dropped]


def notices(dropped: dict[str, str]) -> list[str]:
    return [
        f"Dropped the '{extra}' feature from this install: `{package}` no longer builds on "
        "this machine (usually a missing compiler for the new Python). Clawksis works "
        f"without it; to bring it back, install the build tools it needs and run "
        f"`clawk pm install --extra {extra}`."
        for extra, package in sorted(dropped.items())
    ]
