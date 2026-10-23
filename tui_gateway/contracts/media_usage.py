"""Clawksis media gallery (``media.*`` over ``media_generations``) and the all-sessions per-model
token aggregate (``usage.by_model``) the chat header combines with ``session.usage``."""

from __future__ import annotations

from typing import Literal

from .base import Params, Result
from .common import OpenModel
from .registry import method

# ── media.* ───────────────────────────────────────────────────────────────────────────────────


class MediaItem(OpenModel):
    """One ``media_generations`` row (``tui_gateway/server.py::_media_list``)."""

    id: int | str
    session_id: str | None = None
    message_id: int | str | None = None
    media_type: str | None = None
    status: str | None = None
    file_path: str | None = None
    original_url: str | None = None
    file_size_bytes: int | None = None
    width: int | None = None
    height: int | None = None
    prompt: str | None = None
    model: str | None = None
    provider: str | None = None
    created_at: float | None = None


class MediaListParams(Params):
    limit: int | None = None
    offset: int | None = None
    media_type: Literal["image", "video"] | None = None
    date_from: float | None = None
    date_to: float | None = None
    model: str | None = None
    session_id: str | None = None
    search: str | None = None
    min_size: int | None = None
    max_size: int | None = None


class MediaListResult(Result):
    items: list[MediaItem]
    total: int
    has_more: bool


method("media.list", params=MediaListParams, result=MediaListResult,
       doc="Generated media (newest first) with filters and pagination.")


class MediaDeleteParams(Params):
    id: int | str


class MediaDeleteResult(Result):
    deleted: bool
    freed_bytes: int
    file_missing: bool


method("media.delete", params=MediaDeleteParams, result=MediaDeleteResult,
       doc="Delete one media entry: its row and its file on disk.")


class MediaStatsParams(Params):
    pass


class MediaStatsResult(Result):
    total_images: int
    total_videos: int
    total_size_bytes: int
    last_7_days: int
    expired_count: int
    ready_count: int


method("media.stats", params=MediaStatsParams, result=MediaStatsResult,
       doc="Aggregate counts and size for the media gallery header.")

# ── usage.by_model ────────────────────────────────────────────────────────────────────────────


class ModelUsageRow(Result):
    model: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    reasoning_tokens: int
    total_tokens: int
    cost_usd: float
    sessions_count: int


class UsageByModelParams(Params):
    pass


class UsageByModelResult(Result):
    models: list[ModelUsageRow]
    total_tokens: int
    total_cost_usd: float


method("usage.by_model", params=UsageByModelParams, result=UsageByModelResult,
       doc="Token usage and cost across every stored session, grouped by model.")
