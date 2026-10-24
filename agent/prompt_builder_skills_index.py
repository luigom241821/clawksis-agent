"""Rendering of the ``## Skills`` system-prompt block (sibling of ``agent.prompt_builder``).

Pure text assembly: ``prompt_builder._build_skills_system_prompt_inner`` resolves, filters and
caches the skill rows; this module only turns them into the block the model reads. The block is
built once at session start and never re-rendered mid-conversation (prompt-caching invariant).
"""

from __future__ import annotations

# Fork: each row also carries the skill's tags as keywords so the model recognises a skill from a
# request phrased in other words (or another language); the description alone is capped at 60 chars.
_MAX_INDEX_KEYWORDS = 8


def _index_summary(
    name: str, description: str, tags: list[str], category: str = ""
) -> str:
    """``description [kw, ...]`` with the tags the row (name, description, category) doesn't already say."""
    said = (
        f"{name} {description} {category}".lower().replace("-", " ").replace("/", " ")
    )
    seen: set[str] = set()
    keywords: list[str] = []
    for tag in tags:
        key = tag.lower().replace("-", " ")
        if tag and key not in seen and key not in said:
            seen.add(key)
            keywords.append(tag)
    if not keywords:
        return description
    return f"{description} [{', '.join(keywords[:_MAX_INDEX_KEYWORDS])}]".strip()


def _label_visible_entries(
    visible_entries: list[dict], skills_by_category: dict[str, list[tuple[str, str]]]
) -> None:
    """Index rows under each entry's ``load_name`` (what skill_view accepts)."""
    from agent.skill_utils import TIER_PROJECT

    for entry in (e for e in visible_entries if e["load_name"]):
        category = entry.get("category") or "general"
        desc = _index_summary(
            entry["load_name"],
            entry.get("description", ""),
            entry.get("tags") or [],
            category,
        )
        if entry["tier"] == TIER_PROJECT:
            desc = f"[project] {desc}".strip()
        skills_by_category.setdefault(category, []).append((entry["load_name"], desc))


def _render_skills_index(
    skills_by_category: dict[str, list[tuple[str, str]]],
    category_descriptions: dict[str, str],
    compact_categories: frozenset[str] | None,
    available_tools: set[str] | None,
    unloadable: list[str] = (),
) -> str:
    """Render the ## Skills block; "" when there is nothing to list. *unloadable* names (different skills
    sharing a name AND relative path within one tier — one root or several) get a rename note instead of a row skill_view would refuse."""
    if not skills_by_category:
        return ""
    # Demoted categories collapse to one names-only line. NEVER drop entries — agent-created skills are the
    # model's project memory and it won't rediscover them via skills_list. Nested categories follow their parent.
    demoted = frozenset(
        cat
        for cat in skills_by_category
        if cat.split("/", 1)[0] in (compact_categories or frozenset())
    )
    hidden_note = (
        (
            "\n(Categories marked [names only] are outside the current coding "
            "context, so their descriptions are omitted — the skills work "
            "normally and load with skill_view(name) as usual.)"
        )
        if demoted
        else ""
    )
    if unloadable:
        hidden_note += (
            f"\n(A copy of {', '.join(unloadable)} is not listed: it shares both its name and its path "
            "with a different skill in the same skills directory tier (e.g. another external_dirs entry), "
            "so skill_view cannot load it — rename one.)"
        )
    # Don't name web_search when the session has no web tools (dangling reference).
    _basic_tools = (
        "terminal"
        if available_tools is not None and "web_search" not in available_tools
        else "web_search or terminal"
    )
    index_lines = []
    for category in sorted(skills_by_category):
        entries = skills_by_category[category]
        if category in demoted:
            index_lines.append(
                f"  {category} [names only]: {', '.join(sorted({n for n, _ in entries}))}"
            )
            continue
        cat_desc = category_descriptions.get(category, "")
        index_lines.append(
            f"  {category}: {cat_desc}" if cat_desc else f"  {category}:"
        )
        seen = set()
        for name, desc in sorted(
            entries, key=lambda x: x[0]
        ):  # stable: first entry per name wins
            if name not in seen:
                seen.add(name)
                index_lines.append(f"    - {name}: {desc}" if desc else f"    - {name}")
    from agent.oneshot_footprint import (
        ONESHOT_SKILLS_LOAD_GUIDANCE,
        is_single_query_session,
    )

    if is_single_query_session():
        return (
            ONESHOT_SKILLS_LOAD_GUIDANCE
            + "\n<available_skills>\n"
            + "\n".join(index_lines)
            + "\n</available_skills>"
            + hidden_note
        )
    return (
        "## Skills\n"
        "Before replying, scan the skills below. If a skill matches or is even partially relevant to your "
        "task, you MUST load it with skill_view(name) and follow its instructions. Err on the side of "
        "loading — it is always better to have context you don't need than to miss critical steps, pitfalls, "
        "or established workflows. Skills contain specialized knowledge — API endpoints, tool-specific "
        "commands, and proven workflows that outperform general-purpose approaches. Load the skill "
        f"even if you think you could handle the task with basic tools like {_basic_tools}. "
        "Skills also encode the user's preferred approach, conventions, and quality standards for tasks like "
        "code review, planning, and testing — load them even for tasks you already know how to do, because "
        "the skill defines how it should be done here.\n"
        # Fork: goal-phrased requests (often not in English) and "what can you do?" questions were
        # answered from general knowledge although a listed skill covered them.
        "Match by meaning, not wording: users describe goals in their own words and in any language "
        "(a price forecast, their broker portfolio, a contract to review) without naming a skill; each "
        "line below is a short English summary, usually followed by [keywords]. When the user asks what "
        "you can do or whether you can help with something, answer from this list — it is what this "
        "installation can actually do — and name the relevant skills instead of answering from general "
        "knowledge. A line is only a summary: before describing a skill in detail (what it does, what it "
        "needs, how to use it), load it with skill_view and answer from its content.\n"
        "If a skill has issues, fix it with skill_manage(action='patch').\n"
        "After difficult/iterative tasks, offer to save as a skill. If a skill you loaded was missing steps, "
        "had wrong commands, or needed pitfalls you discovered, update it before finishing.\n"
        "\n"
        "<available_skills>\n" + "\n".join(index_lines) + "\n"
        "</available_skills>\n\n"
        "Only proceed without loading a skill if genuinely none are relevant to the task."
        + hidden_note
    )
