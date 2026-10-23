"""Behavior tests for clawk_state._wal_reset_repair_hint.

The WAL-reset corruption warning's repair hint must match what the user's
install can actually do: source checkouts get the venv-setup step, packaged
installs get their steward's update command (#75153).
"""

from unittest.mock import patch

import clawk_state_wal as clawk_state


def _hint_for(method):
    with patch("clawk_cli.config.detect_install_method", return_value=method), \
         patch("clawk_cli.config.recommended_update_command_for_method",
               return_value=f"CMD-{method}"):
        return clawk_state._wal_reset_repair_hint()


def test_source_checkout_gets_venv_setup_hint():
    assert _hint_for("source") == "CMD-source"


def test_git_install_gets_clawk_managed_hint():
    assert _hint_for("git") == (
        "Clawksis-managed installs can repair the embedded runtime with `CMD-git`"
    )


def test_docker_gets_container_image_hint():
    assert _hint_for("docker") == "update the container image with `CMD-docker`"


def test_nix_passes_through_recommended_command():
    assert _hint_for("nix") == "CMD-nix"


def test_hint_falls_back_when_detection_fails():
    with patch("clawk_cli.config.detect_install_method",
               side_effect=RuntimeError("boom")):
        hint = clawk_state._wal_reset_repair_hint()
    assert "SQLite 3.51.3+" in hint
