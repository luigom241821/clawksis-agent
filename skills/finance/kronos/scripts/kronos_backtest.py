#!/usr/bin/env python3
"""Honesty check: walk-forward Kronos vs the naive "repeat the last close" forecast.

For each origin in the instrument's recent history, Kronos sees only the bars up to
that origin and forecasts the next --horizon closes; the naive baseline repeats the
origin's close. Reports MAE/MAPE (all steps), direction hit-rate at the horizon, the
"always up" base rate, MAE skill vs naive, and a plain-language verdict the agent should
relay before presenting any Kronos forecast as useful.

Origins are batched into a few predict_batch calls (one process, few model calls).
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Any

_SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from _kronos_common import (
    DISCLAIMER,
    MAX_CONTEXT,
    Bar,
    SkillError,
    dump_json,
    reexec_in_skill_venv,
    render_table,
    require_state,
    run_cli,
    score_origins,
    verdict,
)
from kronos_forecast import _bounded, add_data_args, add_model_args, load_input

MIN_ORIGINS = 5


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Walk-forward Kronos vs naive last-close backtest."
    )
    add_data_args(parser)
    parser.add_argument(
        "--origins",
        type=_bounded(MIN_ORIGINS, 200),
        default=20,
        help="forecast origins to test",
    )
    parser.add_argument(
        "--horizon",
        type=_bounded(1, 60),
        default=5,
        help="bars ahead scored at each origin",
    )
    parser.add_argument(
        "--stride",
        type=_bounded(1, 500),
        default=None,
        help="bars between origins (default: horizon)",
    )
    add_model_args(parser, samples=4, lookback=256)
    parser.add_argument("--format", choices=("table", "json"), default="table")
    return parser


def plan_origins(
    n_bars: int, lookback: int, horizon: int, origins: int, stride: int
) -> list[int]:
    """Indices of the last observed bar per origin, ascending; each has a full future."""
    last = n_bars - 1 - horizon
    picks = [last - i * stride for i in range(origins)]
    feasible = sorted(i for i in picks if i >= lookback - 1)
    if len(feasible) < MIN_ORIGINS:
        raise SkillError(
            f"History too short: {n_bars} bars allow {len(feasible)} origin(s) with lookback "
            f"{lookback}, horizon {horizon}, stride {stride} (need {MIN_ORIGINS}).",
            hint="Lower --lookback/--stride/--origins or fetch more bars.",
        )
    return feasible


def origin_windows(
    bars: list[Bar], indices: list[int], lookback: int, horizon: int
) -> list[dict[str, Any]]:
    return [
        {
            "window": bars[i - lookback + 1 : i + 1],
            "future_ts": [b.ts for b in bars[i + 1 : i + 1 + horizon]],
            "actual": [b.close for b in bars[i + 1 : i + 1 + horizon]],
            "last_close": bars[i].close,
            "origin_ts": bars[i].ts.isoformat(),
        }
        for i in indices
    ]


def render_text(result: dict[str, Any]) -> str:
    k, n = result["metrics"]["kronos"], result["metrics"]["naive_last_close"]
    rows = [
        ("Kronos", k["mae"], k["mape_pct"], k["direction_hit_rate"]),
        ("repeat last close", n["mae"], n["mape_pct"], None),
        ("always up (base rate)", None, None, result["metrics"]["always_up_hit_rate"]),
    ]
    label = result.get("symbol") or Path(str(result.get("input", "series"))).stem
    return "\n".join(
        [
            f"{label}: {result['origins']} origins, horizon {result['horizon']}, lookback "
            f"{result['lookback']}, {result['model']} ({result['first_origin']} → {result['last_origin']})",
            render_table(("forecaster", "MAE", "MAPE_%", "direction_hit"), rows),
            f"MAE skill vs naive: {result['metrics']['mae_skill_vs_naive']:+.1%}",
            f"verdict: {result['verdict']} — {result['verdict_text']}",
            *(f"warning: {w}" for w in result["warnings"]),
            result["disclaimer"],
        ]
    )


def run(args: argparse.Namespace, argv: list[str]) -> int:
    if not args.dry_run:
        code = reexec_in_skill_venv(Path(__file__).resolve(), argv, args.timeout)
        if code is not None:
            return code
    stride = args.stride or args.horizon
    lookback = min(args.lookback, MAX_CONTEXT[args.model])
    needed = lookback + (args.origins - 1) * stride + args.horizon + 1
    bars, meta, warnings = load_input(args, min(needed, 1000))
    indices = plan_origins(len(bars), lookback, args.horizon, args.origins, stride)
    if len(indices) < args.origins:
        warnings.append(
            f"only {len(indices)} of {args.origins} origins fit the available history"
        )
    windows = origin_windows(bars, indices, lookback, args.horizon)
    base = {
        "ok": True,
        **meta,
        "origins": len(windows),
        "horizon": args.horizon,
        "lookback": lookback,
    }
    base.update(
        {
            "first_origin": windows[0]["origin_ts"],
            "last_origin": windows[-1]["origin_ts"],
        }
    )
    if args.dry_run:
        print(
            dump_json({**base, "dry_run": True, "stride": stride, "warnings": warnings})
        )
        return 0
    state = require_state()
    from _kronos_model import load_predictor, predict_paths

    started = time.monotonic()
    predictor = load_predictor(
        state, args.model, device=args.device, threads=args.threads, seed=args.seed
    )
    paths = predict_paths(
        predictor,
        [w["window"] for w in windows],
        [w["future_ts"] for w in windows],
        args.horizon,
        sample_count=args.samples,  # mean of K samples per origin, like a forecast's mean path
        temperature=args.temperature,
        top_p=args.top_p,
    )
    scored = [
        {
            "last_close": w["last_close"],
            "actual": w["actual"],
            "kronos": [row["close"] for row in path],
        }
        for w, path in zip(windows, paths)
    ]
    metrics = score_origins(scored)
    code, text = verdict(metrics)
    result = {
        **base,
        "model": f"Kronos-{args.model}",
        "samples": args.samples,
        "stride": stride,
        "metrics": metrics,
        "verdict": code,
        "verdict_text": text,
        "warnings": warnings,
        "elapsed_s": round(time.monotonic() - started, 1),
        "disclaimer": DISCLAIMER,
    }
    print(render_text(result) if args.format == "table" else dump_json(result))
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    args = build_parser().parse_args(argv)
    return run_cli(lambda: run(args, argv))


if __name__ == "__main__":
    sys.exit(main())
