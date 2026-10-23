"""Resolve CLAWK_HOME for standalone skill scripts.

Skill scripts may run outside the Clawksis process (system Python, nix env,
CI) where ``clawk_constants`` is not importable.  This module provides the
same ``get_clawk_home()`` contract without requiring it on ``sys.path``.

When ``clawk_constants`` IS available it is used directly so profile
resolution and any future enhancements are picked up automatically.
"""

from __future__ import annotations

import os
from pathlib import Path

try:
    from clawk_constants import get_clawk_home
except (ModuleNotFoundError, ImportError):

    def get_clawk_home() -> Path:
        """Return the Clawksis home directory (default: ``~/.clawksis``)."""
        val = os.environ.get("CLAWK_HOME", "").strip()
        return Path(val) if val else Path.home() / ".clawksis"
