"""Skills index rows carry each skill's tags as keywords (fork).

The 60-char description alone left the model unable to recognise a skill from a request phrased
in other words; the tags it does not already say ride along as ``[keywords]``.
"""

import pytest

from agent.prompt_builder import (
    build_skills_system_prompt,
    clear_skills_system_prompt_cache,
)


@pytest.fixture(autouse=True)
def _isolated_skills_home(monkeypatch, tmp_path):
    monkeypatch.setenv("CLAWK_HOME", str(tmp_path))
    clear_skills_system_prompt_cache(clear_snapshot=True)
    yield tmp_path
    clear_skills_system_prompt_cache(clear_snapshot=True)


def _write_skill(home, name, frontmatter_extra=""):
    d = home / "skills" / "finance" / name
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: Forecast stock prices\n{frontmatter_extra}---\n\nBody.\n",
        encoding="utf-8",
    )


def _row(index, name):
    return next(
        line.strip()
        for line in index.splitlines()
        if line.strip().startswith(f"- {name}:")
    )


def test_row_adds_only_tags_the_summary_does_not_already_say(_isolated_skills_home):
    _write_skill(
        _isolated_skills_home,
        "kronos",
        "metadata:\n  clawk:\n    tags: [Markets, forecast, eToro, Markets, Stock-Prices, Finance]\n",
    )

    row = _row(build_skills_system_prompt(), "kronos")

    # "forecast"/"Stock-Prices" are in the summary, "Finance" is the category; Markets is deduped.
    assert row == "- kronos: Forecast stock prices [Markets, eToro]"


def test_top_level_tags_are_used_and_capped(_isolated_skills_home):
    tags = ", ".join(f"kw{i}" for i in range(12))
    _write_skill(_isolated_skills_home, "many-tags", f"tags: [{tags}]\n")

    row = _row(build_skills_system_prompt(), "many-tags")

    assert row.endswith("[kw0, kw1, kw2, kw3, kw4, kw5, kw6, kw7]")


def test_skill_without_tags_keeps_its_plain_row(_isolated_skills_home):
    _write_skill(_isolated_skills_home, "plain")

    assert (
        _row(build_skills_system_prompt(), "plain") == "- plain: Forecast stock prices"
    )


def test_keywords_survive_the_disk_snapshot(_isolated_skills_home):
    _write_skill(
        _isolated_skills_home, "kronos", "metadata:\n  clawk:\n    tags: [eToro]\n"
    )
    first = build_skills_system_prompt()
    assert (_isolated_skills_home / ".skills_prompt_snapshot.json").exists()

    # Drop only the in-process cache: the next build is served from the disk snapshot.
    clear_skills_system_prompt_cache()
    second = build_skills_system_prompt()

    assert _row(second, "kronos") == "- kronos: Forecast stock prices [eToro]"
    assert second == first


def test_malformed_metadata_block_does_not_break_the_index(_isolated_skills_home):
    _write_skill(_isolated_skills_home, "odd", "metadata:\n  clawk: not-a-mapping\n")
    _write_skill(_isolated_skills_home, "kronos", "tags: [eToro]\n")

    index = build_skills_system_prompt()

    assert _row(index, "odd") == "- odd: Forecast stock prices"
    assert _row(index, "kronos") == "- kronos: Forecast stock prices [eToro]"
