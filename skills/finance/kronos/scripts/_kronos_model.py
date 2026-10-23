"""Torch-side helpers for the Kronos skill; imported only inside the skill venv.

Wires the pinned upstream code (``src/<sha>/model``) to local weights with the guards the
upstream examples lack: the source is re-verified against its pin before import, both
modules are switched to ``eval()`` (with huggingface_hub < 2 they load in training mode,
leaving dropout on; upstream issue #415), loading is offline, and the generic package name
``model`` must resolve to the pinned checkout.
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

from _kronos_common import PRICE_COLUMNS, UPSTREAM_FILES, Bar, SkillError

_DEVICES = {"cpu": "cpu", "cuda": "cuda:0"}


def _verify_source(src_dir: Path) -> None:
    for name, digest in UPSTREAM_FILES.items():
        path = src_dir / name
        if (
            not path.is_file()
            or hashlib.sha256(path.read_bytes()).hexdigest() != digest
        ):
            raise SkillError(
                f"Pinned Kronos source failed verification ({name}).",
                hint="Re-run kronos_setup.py --force.",
            )


def import_upstream(src_dir: Path) -> Any:
    """Import the pinned ``model`` package, refusing any other module of that name."""
    _verify_source(src_dir)
    for name in [m for m in sys.modules if m == "model" or m.startswith("model.")]:
        del sys.modules[name]
    sys.path.insert(0, str(src_dir))
    import model as upstream  # the pinned checkout, first on sys.path

    origin = Path(getattr(upstream, "__file__", "") or "").resolve()
    if src_dir.resolve() not in origin.parents:
        raise SkillError(
            f"`import model` resolved to {origin}, not the pinned Kronos source."
        )
    return upstream


def resolve_device(device: str, torch: Any) -> str:
    if device == "auto":
        return "cuda:0" if torch.cuda.is_available() else "cpu"
    return _DEVICES[device]


def load_predictor(
    state: dict[str, Any],
    model_name: str,
    *,
    device: str,
    threads: int | None,
    seed: int,
) -> Any:
    entry = (state.get("models") or {}).get(model_name)
    if not entry:
        raise SkillError(
            f"Kronos-{model_name} is not installed.",
            hint=f"Run kronos_setup.py --model {model_name}.",
        )
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    import torch

    if threads:
        torch.set_num_threads(threads)
    torch.manual_seed(seed)
    upstream = import_upstream(Path(state["src_dir"]))
    # huggingface_hub prints progress to stdout, which would corrupt --format json output.
    with contextlib.redirect_stdout(sys.stderr):
        tokenizer = upstream.KronosTokenizer.from_pretrained(entry["tokenizer_dir"])
        model = upstream.Kronos.from_pretrained(entry["model_dir"])
    tokenizer.eval()
    model.eval()
    return upstream.KronosPredictor(
        model,
        tokenizer,
        device=resolve_device(device, torch),
        max_context=int(entry["max_context"]),
    )


def _frame(window: Sequence[Bar], pd: Any) -> Any:
    columns = {c: [getattr(b, c) for b in window] for c in PRICE_COLUMNS}
    if all(b.volume is not None for b in window):
        columns["volume"] = [b.volume for b in window]
    return pd.DataFrame(columns)


def _rows(frame: Any, horizon: int) -> list[dict[str, float]]:
    values = {
        c: [float(v) for v in frame[c].tolist()] for c in (*PRICE_COLUMNS, "volume")
    }
    return [{c: values[c][i] for c in values} for i in range(horizon)]


def predict_paths(
    predictor: Any,
    windows: Sequence[Sequence[Bar]],
    future: Sequence[Sequence[datetime]],
    horizon: int,
    *,
    sample_count: int,
    temperature: float,
    top_p: float,
    batch_size: int = 16,
) -> list[list[dict[str, float]]]:
    """One path per window. ``sample_count`` > 1 averages that many samples per path
    (upstream behaviour); pass K copies of a window with ``sample_count=1`` for K paths."""
    import pandas as pd

    frames = [_frame(w, pd) for w in windows]
    x_ts = [pd.Series(pd.to_datetime([b.ts for b in w])) for w in windows]
    y_ts = [pd.Series(pd.to_datetime(list(f))) for f in future]
    paths: list[list[dict[str, float]]] = []
    for start in range(0, len(frames), batch_size):
        stop = start + batch_size
        with contextlib.redirect_stdout(sys.stderr):
            predictions = predictor.predict_batch(
                frames[start:stop],
                x_ts[start:stop],
                y_ts[start:stop],
                pred_len=horizon,
                T=temperature,
                top_k=0,  # top_k > 0 silently disables top_p upstream
                top_p=top_p,
                sample_count=sample_count,
                verbose=False,
            )
        paths.extend(_rows(frame, horizon) for frame in predictions)
    return paths


def render_chart(
    history: Sequence[Bar],
    result: dict[str, Any],
    path: Path,
    title: str,
) -> Path:
    """History tail, mean forecast and p10–p90 band as a PNG (sized for chat apps)."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    rows = result["forecast"]
    tail = list(history)[-max(60, 3 * len(rows)) :]
    future_ts = [datetime.fromisoformat(r["timestamp"]) for r in rows]
    fig, ax = plt.subplots(figsize=(10, 5.5), dpi=120)
    ax.plot(
        [b.ts for b in tail],
        [b.close for b in tail],
        color="#4a5568",
        lw=1.4,
        label="history",
    )
    ax.plot(
        [tail[-1].ts, *future_ts],
        [tail[-1].close, *(r["close"] for r in rows)],
        color="#2b6cb0",
        lw=2,
        label="Kronos mean",
    )
    ax.fill_between(
        future_ts,
        [r["close_p10"] for r in rows],
        [r["close_p90"] for r in rows],
        color="#90cdf4",
        alpha=0.45,
        label="p10–p90 of samples (too narrow in tests)",
    )
    ax.axvline(tail[-1].ts, color="#a0aec0", ls="--", lw=1)
    ax.set_title(title, fontsize=11)
    ax.grid(alpha=0.25)
    ax.legend(loc="best", fontsize=8)
    fig.text(
        0.01,
        0.01,
        "Not financial advice. Research model; verify with kronos_backtest.py.",
        fontsize=7,
        color="#718096",
    )
    fig.autofmt_xdate()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path
