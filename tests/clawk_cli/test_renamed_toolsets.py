"""Back-compat for toolsets the fork renamed (``toolset_validation.RENAMED_TOOLSETS``).

The webhook platform bundle used to be ``clawksis-webhook``; every platform bundle is now
``clawk-<platform>``. A config saved by an older Clawksis (``platform_toolsets.webhook:
[clawksis-webhook]``) must keep resolving to the same tools and must not be flagged as an
unknown toolset.
"""

from clawk_cli.toolset_validation import (
    RENAMED_TOOLSETS,
    saved_toolset_resolver,
    validate_platform_toolsets,
)
from clawk_cli.tools_config import _get_platform_tools
from toolsets import TOOLSETS


def test_every_rename_targets_a_registered_platform_bundle():
    for old, new in RENAMED_TOOLSETS.items():
        assert new in TOOLSETS, (old, new)
        assert new.startswith("clawk-") and old not in TOOLSETS


def test_old_webhook_bundle_name_resolves_like_the_new_one():
    def tools(name: str) -> set[str]:
        config = {"platform_toolsets": {"webhook": [name]}}
        return _get_platform_tools(config, "webhook", include_default_mcp_servers=False)

    assert tools("clawk-webhook")
    assert tools("clawksis-webhook") == tools("clawk-webhook")


def test_old_webhook_bundle_name_is_not_an_unknown_toolset():
    warnings = validate_platform_toolsets(
        {"webhook": ["clawksis-webhook"]}, saved_toolset_resolver({})
    )
    assert warnings == []
