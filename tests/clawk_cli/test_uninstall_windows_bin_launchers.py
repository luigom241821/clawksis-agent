"""Uninstall must not leave a dangling ``clawk`` command on Windows.

Every uninstall mode deletes the code checkout, but the launcher copies
staged onto PATH in the managed binary dir (the default Clawksis root's
``bin``) live outside it. A surviving launcher makes ``clawk`` in a new
terminal resolve and then error on its missing venv target — worse than
command-not-found. The dir is wholly clawk-owned (pm keeps uv in its own
store entry), so the sweep takes everything in it.

Platform verdicts are injected parameters (input→output, not host fakes).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from clawk_cli import uninstall


@pytest.fixture
def managed_bin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Default-root ``bin`` holding staged launcher copies."""
    home = tmp_path / "clawk"
    bin_dir = home / "bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "clawk.exe").write_bytes(b"MZ launcher")
    (bin_dir / "clawk-acp.cmd").write_text("@echo off\r\n", encoding="ascii")
    monkeypatch.setenv("CLAWK_HOME", str(home))
    return bin_dir


def test_removes_the_whole_managed_bin_dir(managed_bin: Path):
    removed = uninstall.remove_windows_bin_launchers(windows=True)

    assert sorted(p.name for p in removed) == ["clawk-acp.cmd", "clawk.exe"]
    assert not managed_bin.exists()


def test_anchors_on_default_root_not_profile_home(
    managed_bin: Path, monkeypatch: pytest.MonkeyPatch
):
    """The launcher dir is per-machine; a profile CLAWK_HOME must not
    redirect the sweep into ``profiles/<name>/bin``."""
    home = managed_bin.parent
    monkeypatch.setenv("CLAWK_HOME", str(home / "profiles" / "work"))

    removed = uninstall.remove_windows_bin_launchers(windows=True)

    assert sorted(p.name for p in removed) == ["clawk-acp.cmd", "clawk.exe"]
    assert not (managed_bin / "clawk.exe").exists()


def test_noop_on_posix(managed_bin: Path):
    assert uninstall.remove_windows_bin_launchers(windows=False) == []
    assert (managed_bin / "clawk.exe").exists()


def test_noop_when_no_bin_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    home = tmp_path / "clawk"
    home.mkdir()
    monkeypatch.setenv("CLAWK_HOME", str(home))

    assert uninstall.remove_windows_bin_launchers(windows=True) == []
