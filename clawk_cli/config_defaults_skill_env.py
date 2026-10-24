"""``OPTIONAL_ENV_VARS`` entries for secrets that bundled skills consume (pure-data leaf).

category="skill" (not "tool") so the terminal env scrub (``tools/environments/local_env_policy.py``)
does NOT strip them: skill scripts run in ``terminal``, and ``tools/env_passthrough.py`` forwards
a loaded skill's declared ``required_environment_variables`` (it refuses "tool" names). Spread
into ``config_defaults.OPTIONAL_ENV_VARS`` at their original position.
"""

from clawk_cli.config_defaults_env import _skill

SKILL_ENV_VARS = {
    "NOTION_API_KEY": _skill(
        "Notion integration token (used by the `notion` skill)",
        "Notion API key",
        "https://www.notion.so/my-integrations",
    ),
    "LINEAR_API_KEY": _skill(
        "Linear personal API key (used by the `linear` skill)",
        "Linear API key",
        "https://linear.app/settings/account/security",
    ),
    "AIRTABLE_API_KEY": _skill(
        "Airtable personal access token (used by the `airtable` skill)",
        "Airtable API key",
        "https://airtable.com/create/tokens",
    ),
    "TENOR_API_KEY": _skill(
        "Tenor API key for GIF search (used by the `gif-search` skill)",
        "Tenor API key",
        "https://developers.google.com/tenor/guides/quickstart",
    ),
    "ETORO_API_KEY": _skill(
        "eToro Public API key, sent as x-api-key (market data, portfolio and, when enabled "
        "in config.yaml, limited trading for the `kronos` skill)",
        "eToro public API key",
        "https://api-portal.etoro.com",
        help="eToro > Settings > Trading > API Key Management; pair it with ETORO_USER_KEY",
    ),
    "ETORO_USER_KEY": _skill(
        "eToro user key, sent as x-user-key (market data, portfolio and, when enabled in "
        "config.yaml, limited trading for the `kronos` skill)",
        "eToro user key",
        "https://api-portal.etoro.com",
        help="Shown once when the key is created; keys belong to the real OR demo account",
    ),
}
