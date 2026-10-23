"""Tests for the clean `clawk update` output helpers.

Phase containment (npm, builds, uv) is pm.progress's job (live tail + failure
tail; ``CLAWK_VERBOSE=1`` streams). `_print_new_commits` renders the What's-new
list shown after a quiet update.
"""

from __future__ import annotations

import subprocess

from clawk_cli.main import _print_new_commits


def _init_repo(root):
    git = ["git"]
    subprocess.run(git + ["init", "-q"], cwd=root, check=True)
    subprocess.run(
        git + ["config", "user.email", "t@example.com"], cwd=root, check=True
    )
    subprocess.run(git + ["config", "user.name", "Tester"], cwd=root, check=True)
    subprocess.run(git + ["config", "commit.gpgsign", "false"], cwd=root, check=True)
    return git


def _head(git, root):
    return subprocess.run(
        git + ["rev-parse", "HEAD"], cwd=root, capture_output=True, text=True,
        check=False,
    ).stdout.strip()


def test_print_new_commits_lists_pulled_commits(capsys, tmp_path):
    git = _init_repo(tmp_path)
    (tmp_path / "a.txt").write_text("1", encoding="utf-8")
    subprocess.run(git + ["add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(git + ["commit", "-qm", "first"], cwd=tmp_path, check=True)
    old = _head(git, tmp_path)

    (tmp_path / "b.txt").write_text("2", encoding="utf-8")
    subprocess.run(git + ["add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(
        git + ["commit", "-qm", "feat: second thing"], cwd=tmp_path, check=True
    )

    _print_new_commits(git, tmp_path, old)
    out = capsys.readouterr().out
    assert "What's new" in out
    assert "1 new commit" in out
    assert "feat: second thing" in out


def test_print_new_commits_noop_when_range_empty(capsys, tmp_path):
    git = _init_repo(tmp_path)
    (tmp_path / "a.txt").write_text("1", encoding="utf-8")
    subprocess.run(git + ["add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(git + ["commit", "-qm", "only"], cwd=tmp_path, check=True)
    head = _head(git, tmp_path)

    _print_new_commits(git, tmp_path, head)  # old == HEAD -> empty range
    assert "What's new" not in capsys.readouterr().out


def test_print_new_commits_noop_when_sha_missing(capsys, tmp_path):
    _print_new_commits(["git"], tmp_path, None)
    assert capsys.readouterr().out == ""
