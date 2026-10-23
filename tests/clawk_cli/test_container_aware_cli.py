"""Tests for container-aware CLI routing (NixOS container mode).

When container.enable = true in the NixOS module, the activation script
writes a .container-mode metadata file. The host CLI detects this and
execs into the container instead of running locally.
"""

import os
from unittest.mock import MagicMock, patch

import pytest

from clawk_cli.config import (
    get_container_exec_info,
)


# =============================================================================
# get_container_exec_info
# =============================================================================


@pytest.fixture
def container_env(tmp_path, monkeypatch):
    """Set up a fake CLAWK_HOME with .container-mode file."""

    clawk_home = tmp_path / ".clawksis"
    clawk_home.mkdir()
    monkeypatch.setenv("CLAWK_HOME", str(clawk_home))
    monkeypatch.delenv("CLAWK_DEV", raising=False)

    container_mode = clawk_home / ".container-mode"
    container_mode.write_text(
        "# Written by NixOS activation script. Do not edit manually.\n"
        "backend=podman\n"
        "container_name=clawksis-agent\n"
        "exec_user=clawk\n"
        "clawk_bin=/data/current-package/bin/clawk\n"
    )
    return clawk_home


def test_get_container_exec_info_returns_metadata(container_env):
    """Reads .container-mode and returns all fields including exec_user."""
    with patch("clawk_constants.is_container", return_value=False):
        info = get_container_exec_info()

    assert info is not None
    assert info["backend"] == "podman"
    assert info["container_name"] == "clawksis-agent"
    assert info["exec_user"] == "clawk"
    assert info["clawk_bin"] == "/data/current-package/bin/clawk"


# =============================================================================
# exec_in_container (clawk_cli/main_container.py)
# =============================================================================


@pytest.fixture
def docker_container_info():
    return {
        "backend": "docker",
        "container_name": "clawksis-agent",
        "exec_user": "clawk",
        "clawk_bin": "/data/current-package/bin/clawk",
    }


def test_exec_in_container_calls_execvp(docker_container_info):
    """Verifies os.execvp is called with correct args: runtime, tty flags,
    user, env vars, container name, binary, and CLI args."""
    from clawk_cli.main_container import exec_in_container

    with (
        patch("shutil.which", return_value="/usr/bin/docker"),
        patch("subprocess.run") as mock_run,
        patch("sys.stdin") as mock_stdin,
        patch("os.execvp") as mock_execvp,
        patch.dict(
            os.environ, {"TERM": "xterm-256color", "LANG": "en_US.UTF-8"}, clear=False
        ),
    ):
        mock_stdin.isatty.return_value = True
        mock_run.return_value = MagicMock(returncode=0)

        exec_in_container(docker_container_info, ["chat", "-m", "opus"])

    mock_execvp.assert_called_once()
    cmd = mock_execvp.call_args[0][1]
    assert cmd[0] == "/usr/bin/docker"
    assert cmd[1] == "exec"
    assert "-it" in cmd
    idx_u = cmd.index("-u")
    assert cmd[idx_u + 1] == "clawk"
    e_indices = [i for i, v in enumerate(cmd) if v == "-e"]
    e_values = [cmd[i + 1] for i in e_indices]
    assert "TERM=xterm-256color" in e_values
    assert "LANG=en_US.UTF-8" in e_values
    assert "clawksis-agent" in cmd
    assert "/data/current-package/bin/clawk" in cmd
    assert "chat" in cmd
