"""An update never fails because of a carried opt-in extra that no longer builds.

Reported live: `clawk update` on a Linux laptop without clang++ died building python-olm
(pulled by the carried ``matrix`` extra, no cp314 wheel). The update path now drops the extra
uv blames, says so, and finishes; a deliberate install of that extra still fails loudly.
The E2E case runs the real pm.install.sync_venv transaction against a temp CLAWK_HOME with a
fake core whose extra depends on a local package that refuses to build (uv works offline).
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import pm.workspace as ws
from pm.extra_eviction import blamed_extras

# The tail the user saw (uv 0.13.5 wording).
LIVE_UV_TAIL = (
    "         error: [Errno 2] No such file or directory: 'clang++'\n\n"
    "hint: `python-olm` (v3.2.16) was included because `clawksis-agent[matrix]` (v0.0.0) "
    "depends on `mautrix[encryption]` (v0.21.1) which depends on `python-olm`\n\n"
    "hint: Build failures usually indicate a problem with the package or the build environment"
)


def test_uv_hint_names_the_extra_and_the_package_that_failed():
    assert blamed_extras(LIVE_UV_TAIL, "clawksis-agent") == {"matrix": "python-olm"}
    assert blamed_extras(LIVE_UV_TAIL, "Clawksis_Agent") == {"matrix": "python-olm"}
    assert blamed_extras(LIVE_UV_TAIL, "another-project") == {}
    assert blamed_extras("error: build backend failed", "clawksis-agent") == {}


@pytest.fixture
def broken_extra_core(tmp_path, monkeypatch):
    """Fake core whose ``flaky`` extra needs a package whose build backend always fails."""
    uv = shutil.which("uv")
    if uv is None:
        pytest.skip("uv not on PATH")
    broken = tmp_path / "broken-lib"
    broken.mkdir()
    (broken / "pyproject.toml").write_text(
        '[project]\nname = "broken-lib"\nversion = "1.0"\n'
        '[build-system]\nrequires = []\nbuild-backend = "backend"\nbackend-path = ["."]\n',
        encoding="utf-8",
    )
    (broken / "backend.py").write_text(
        "def get_requires_for_build_wheel(config=None): return []\n"
        "def build_wheel(directory, config=None, metadata=None): "
        "raise SystemExit('clang++ missing')\n",
        encoding="utf-8",
    )
    core = tmp_path / "core"
    core.mkdir()
    (core / "pyproject.toml").write_text(
        '[project]\nname = "fake-core"\nversion = "0.1.0"\n'
        'requires-python = ">=3.11"\ndependencies = []\n'
        '[project.optional-dependencies]\nflaky = ["broken-lib"]\n'
        f'[tool.uv.sources]\nbroken-lib = {{ path = "{broken.as_posix()}" }}\n',
        encoding="utf-8",
    )
    subprocess.run(
        [uv, "lock"], cwd=core, check=True, capture_output=True, text=True, timeout=120
    )
    home = tmp_path / "home"
    home.mkdir()
    (home / "config.yaml").write_text("plugins:\n  enabled: []\n", encoding="utf-8")

    import importlib

    import pm.paths

    install = importlib.import_module("pm.install")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv("CLAWK_HOME", str(home))
    monkeypatch.setenv("CLAWK_RUNTIME_DIR", str(tmp_path / "tools"))
    monkeypatch.setattr(pm.paths, "repo_root", lambda: core)
    monkeypatch.setattr(ws.paths, "repo_root", lambda: core)
    monkeypatch.setattr(install, "lazy_installs_allowed", lambda: True)
    monkeypatch.setattr(
        "pm._uv._toolchain", lambda **kwargs: (Path(uv), Path(sys.executable))
    )
    return core


def test_update_drops_a_carried_extra_that_no_longer_builds(broken_extra_core):
    from pm.environments import runtime_facts_path
    from pm.install import sync_venv, venv_is_current
    from pm.lock import Facts
    from pm.receipt import latest

    # What `clawk update` passes for a main-era install: the extras its old venv carried.
    sync_venv(["flaky"], explicit=True, evict_incompatible_plugins=True)

    recorded = Facts(runtime_facts_path(broken_extra_core), strict=True).get("venv")
    assert "flaky" not in recorded["extras"]
    assert venv_is_current(project_root=broken_extra_core) is True
    warnings = json.dumps(latest().get("warnings"))
    assert "Dropped the 'flaky' feature" in warnings and "broken-lib" in warnings
    assert "clawk pm install --extra flaky" in warnings


def test_a_deliberate_install_of_the_extra_still_fails(broken_extra_core):
    from pm.environment import BuildFailure
    from pm.install import sync_venv

    with pytest.raises(BuildFailure, match="clang\\+\\+ missing|build"):
        sync_venv(["flaky"], explicit=True)
