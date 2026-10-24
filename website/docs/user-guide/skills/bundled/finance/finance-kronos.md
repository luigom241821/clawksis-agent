---
title: "Kronos — Forecast stocks/crypto; eToro data and limited trading"
sidebar_label: "Kronos"
description: "Forecast stocks/crypto; eToro data and limited trading"
---

{/* This page is auto-generated from the skill's SKILL.md by website/scripts/generate-skill-docs.py. Edit the source SKILL.md, not this page. */}

# Kronos

Forecast stocks/crypto; eToro data and limited trading.

## Skill metadata

| | |
|---|---|
| Source | Bundled (installed by default) |
| Path | `skills/finance/kronos` |
| Version | `0.2.0` |
| Author | samuelgradientai-sys, Clawksis |
| License | MIT |
| Platforms | linux, macos, windows |
| Tags | `Finance`, `Forecasting`, `Stocks`, `Crypto`, `eToro`, `Portfolio`, `Trading`, `Time Series` |
| Related skills | [`stocks`](../../optional/finance/finance-stocks.md) |

## Reference: full SKILL.md

:::info
The following is the complete skill definition that Clawksis loads when this skill is triggered. This is what the agent sees as instructions when the skill is active.
:::

# Kronos Skill

Forecasts the next N candles (open/high/low/close/volume) of a stock, ETF, index or crypto
with the open-source Kronos foundation model, running locally on CPU, and pulls candles or
the user's open positions from eToro's Public API. When the user turns trading on, it can
also buy (market, by USD amount, long-only, no leverage) and close positions on its own, inside
hard limits that the script enforces: demo account by default, a per-order cap, and a daily cap
on USD and number of buys. Kronos is a research model that often fails to beat "repeat the last
close", so every forecast ships with a backtest-based honesty check and a not-financial-advice
disclaimer; it is not a live-quote or fundamentals tool.

## When to Use

- "Forecast / predict AAPL for the next 10 days", "what might BTC do in the next 24 hours",
  "next candles for EURUSD", "chart a forecast band for my stock".
- Spanish triggers: "pronóstico de acciones", "predecir velas", "¿qué hará Tesla la próxima
  semana?", "proyección del bitcoin", "predicción del precio", "analizar mi portafolio de
  eToro", "conecta mi cuenta de eToro", "¿vale la pena este modelo para esta acción?".
- Reviewing an eToro portfolio: positions, weights, unrealized P&L, copy-trading, then
  forecasting the largest holdings.
- Judging whether a forecast model adds value for one instrument (walk-forward backtest).
- Trading on eToro when it is enabled: "compra 50 dólares de Apple", "vende mi posición de
  Tesla", "opera automáticamente con Kronos", "cierra la mitad de BTC", "¿cuánto me queda del
  límite de hoy?".
- Not for: leverage, short selling, stop-loss edits or limit orders (not implemented; the user
  does those in the eToro app), live quotes or company fundamentals (the optional `stocks`
  skill covers Yahoo data).

## Prerequisites

- **One-time runtime install** (`kronos_setup.py`): builds a dedicated venv under
  `$CLAWK_HOME/kronos/` with CPU-only PyTorch, the upstream Kronos code pinned to a commit and
  verified file by file (sha256, fail closed), and weights at pinned Hugging Face revisions.
  About 1.2 GB of disk and a few minutes; needs pypi.org, download.pytorch.org,
  codeload.github.com and huggingface.co. It never touches Clawksis' own environment.
- **Hardware**: CPU is enough. Kronos-small (default) peaks around 1 GB of RAM, comfortable
  on a 12 GB VPS; `mini` is lighter and faster; `base` is slow on CPU.
- **Data**: at least 64 chronologically ordered bars, ideally 300–500, from eToro, a CSV
  (timestamps/date, open, high, low, close, optional volume; `;`-delimited decimal-comma
  exports work), or the `stocks` skill's `history` JSON.
- **eToro (optional)**: `ETORO_API_KEY` (public API key) and `ETORO_USER_KEY` in the profile's
  `.env`. Create them in eToro under Settings > Trading > API Key Management; a key belongs to
  one environment (real or demo) and the user key is shown only once. If the user pastes keys
  in chat, save them with `clawk config set ETORO_API_KEY ...` / `clawk config set
  ETORO_USER_KEY ...` through `terminal`, never echo them back, then continue.
- **Trading (optional, off by default)**: the user turns it on with `clawk config set
  skills.config.kronos.trading.enabled true`. Orders go to the **demo** account unless the user
  sets `skills.config.kronos.trading.account real`, and demo trading needs a key pair created in
  the eToro demo (virtual) portfolio. Limits: `max_order_usd` (100), `max_daily_usd` (300) and
  `max_orders_per_day` (5) under the same prefix. The loaded skill shows the current values in
  its `[Skill config]` block. Only the user changes these settings; never change them yourself.

## How to Run

Run every script through the `terminal` tool with `python3` and the full path below
(`${CLAWK_SKILL_DIR}` is expanded when the skill loads; shell variables do not persist
between terminal calls). Forecast and backtest relaunch themselves inside the skill venv.
Output is a chat-ready table by default; `--format json` for automation. Errors come back as
JSON with `error` and `hint`.

```bash
python3 ${CLAWK_SKILL_DIR}/scripts/kronos_setup.py --check
python3 ${CLAWK_SKILL_DIR}/scripts/kronos_forecast.py --etoro AAPL --interval OneDay --horizon 10 --plot auto
```

## Quick Reference

```bash
# runtime (once per profile; idempotent)
python3 ${CLAWK_SKILL_DIR}/scripts/kronos_setup.py --check
python3 ${CLAWK_SKILL_DIR}/scripts/kronos_setup.py
python3 ${CLAWK_SKILL_DIR}/scripts/kronos_setup.py --model mini --pin-on-first-use

# eToro, read-only
python3 ${CLAWK_SKILL_DIR}/scripts/etoro_data.py check
python3 ${CLAWK_SKILL_DIR}/scripts/etoro_data.py search TSLA
python3 ${CLAWK_SKILL_DIR}/scripts/etoro_data.py candles BTC --interval OneHour --count 500 --output btc_1h.csv
python3 ${CLAWK_SKILL_DIR}/scripts/etoro_data.py portfolio --account real --format table

# trading (only when enabled; the script enforces account and limits)
python3 ${CLAWK_SKILL_DIR}/scripts/etoro_trade.py status
python3 ${CLAWK_SKILL_DIR}/scripts/etoro_trade.py positions
python3 ${CLAWK_SKILL_DIR}/scripts/etoro_trade.py buy AAPL --amount 50 --reason "backtest adds_value, +2.1% in 5d" --dry-run
python3 ${CLAWK_SKILL_DIR}/scripts/etoro_trade.py buy AAPL --amount 50 --reason "backtest adds_value, +2.1% in 5d"
python3 ${CLAWK_SKILL_DIR}/scripts/etoro_trade.py close 123456789 --reason "forecast turned down"
python3 ${CLAWK_SKILL_DIR}/scripts/etoro_trade.py close 123456789 --units 0.5 --reason "take half profit"

# honesty check, then forecast
python3 ${CLAWK_SKILL_DIR}/scripts/kronos_backtest.py --etoro AAPL --interval OneDay
python3 ${CLAWK_SKILL_DIR}/scripts/kronos_forecast.py --etoro AAPL --interval OneDay --horizon 10 --plot auto
python3 ${CLAWK_SKILL_DIR}/scripts/kronos_forecast.py --input prices.csv --horizon 5 --format json
python3 ${CLAWK_SKILL_DIR}/scripts/kronos_forecast.py --input prices.csv --dry-run
```

| Knob | Default | Effect on a CPU-only VPS |
|---|---|---|
| `--model` | `small` | `mini` ≈ 5x faster, context 2048; `base` ≈ 4x slower |
| `--lookback` | 400 (backtest 256) | bars of context; cost grows linearly (max 512, mini 2048) |
| `--horizon` | 10 (backtest 5) | candles ahead; cost and error grow with distance |
| `--samples` | 8 (backtest 4) | sampled paths for the band; cost grows linearly |
| `--threads` | all cores | cap it when the VPS also serves the gateway |
| `--calendar` | `auto` | `weekdays`, `24x7` (crypto), `sessions` (intraday stocks) |

Intervals: `OneMinute`, `FiveMinutes`, `TenMinutes`, `FifteenMinutes`, `ThirtyMinutes`,
`OneHour`, `FourHours`, `OneDay`, `OneWeek` (aliases `1d`, `1h`, `15m` ... work).

## Procedure

1. **Pick the data.** eToro symbol (`--etoro`), a user file (inspect it with `read_file`), or
   `stocks` history JSON. Ambiguous symbol (`AAPL` vs `AAPL.24-7`)? Run `etoro_data.py search`
   and use the exact symbol. Keys missing? The script says how to add them; offer the CSV route.
2. **Check the runtime** with `kronos_setup.py --check`. If `setup_needed`, tell the user it is
   a one-time ~1.2 GB download of a few minutes, then run `kronos_setup.py` (add `--model
   mini` only when asked for speed; it needs `--pin-on-first-use`, see Pitfalls).
3. **Run the honesty check first**: `kronos_backtest.py` on the same symbol and interval. Keep
   its `verdict` (`adds_value`, `no_clear_edge`, `worse_than_naive`, `inconclusive`).
4. **Forecast** with a horizon that fits the bar size: daily 5–10, hourly 12–24, 15-minute
   8–16. Add `--plot auto` when the user is on a messaging app.
5. **Present compactly**: last close, close at horizon with % change and direction, the
   p10–p90 band (say it is too narrow), the backtest verdict in one sentence, and the
   disclaimer from the output. On Telegram/WhatsApp use bullets, not tables, and attach the
   chart with `MEDIA:/absolute/path.png` from `chart_path`; use `send_message` only to deliver
   it to a different channel. With `worse_than_naive`, lead with that, not the numbers.
6. **Portfolio review** ("analiza mi portafolio de eToro"): `etoro_data.py portfolio` (add
   `--account demo` for demo keys), summarize cash, weights, concentration, unrealized P&L and
   copy-trading; then forecast the 3–5 largest holdings, one script run each (~1 min on CPU).
   Frame results as scenarios, never as buy/sell instructions.
7. **Recurring forecasts** on request: schedule a `cronjob` that runs the backtest + forecast
   and delivers the summary and chart to the user's channel.
8. **Trading** (only when `etoro_trade.py status` shows `enabled: true`). The user chose
   automatic trading inside limits, so do not ask before each order, but:
   - Buy only when the backtest verdict for that symbol and interval is `adds_value` and the
     forecast points up, or when the user names a specific trade. Never trade on
     `worse_than_naive` or `inconclusive`.
   - Size within the limits from `status` (`usd_left`, `buys_left`); the script refuses the
     rest. Never split one decision into several orders to get around a cap.
   - Sell by closing positions (`positions` lists their ids); closes are not capped.
   - Always pass a one-line `--reason` (verdict + forecast), and after every order tell the
     user what was bought or sold, the amount, the status and why. `submitted` or `placed`
     means eToro has not filled it yet; check `positions` later.
   - Automatic runs on a schedule: a `cronjob` that runs backtest, forecast and, when the rules
     above allow it, `etoro_trade.py`, then reports to the user's channel.

## Pitfalls

- **Not advice, and often no better than naive.** Independent tests (upstream issues #354,
  #375) found Kronos losing to "repeat the last close" and its sampled bands covering ~58% of
  outcomes instead of 90%. Never present a forecast without the backtest verdict.
- **Trading is off until the user turns it on.** If `status` says `enabled: false`, explain
  how the user enables it; do not enable it, raise limits or switch to the real account
  yourself, and never call eToro trading endpoints any other way than `etoro_trade.py`.
- **Limits are hard.** A refused order (`TradingRefused`) is final for today unless the user
  changes the limits. An `unknown` status (network failure) keeps counting toward the daily
  limit: check `positions` before buying again, never resend blindly.
- **Minimums and market hours.** eToro rejects buys under the instrument minimum (HTTP 400);
  stock orders outside market hours stay `placed` until the open.
- **401/403 from eToro**: wrong key, a demo key used with `--account real` (or the reverse), a
  demo key while `trading.account` is `real` (or the reverse), or a key without that
  permission. `etoro_data.py check` shows the granted scopes.
- **eToro candle limits**: at most 1000 bars per request, always ending at the latest bar; the
  still-forming candle is dropped automatically. For longer daily history use `OneWeek` or a CSV.
- **Unverified API details**: the official reference could not be fetched when this skill was
  written; endpoints follow two third-party clients. See `references/etoro-api.md` before
  debugging odd responses.
- **No holiday calendar**: future timestamps skip weekends (or replay intraday sessions) but not
  exchange holidays. Crypto is detected as 24x7 from weekend bars.
- **Mixed adjustments**: do not mix split-adjusted and unadjusted prices in one series.
- **CPU cost** grows with lookback x horizon x samples (no KV cache upstream). Lower `--samples`
  or `--lookback`, or use `--model mini`, when a run nears `--timeout` (default 30 min).
- **mini/base revisions are not pinned yet**; `--pin-on-first-use` records the current Hugging
  Face commit once in `state.json` and later runs load exactly that commit.
- **Keys added mid-conversation** may need a new session (or `clawk gateway restart`) before the
  terminal sees them.
- `pip install kronos` is an unrelated package; never run the upstream web UI or fine-tune
  pipeline (unauthenticated server, pickle loading). Uninstall: delete `$CLAWK_HOME/kronos/`.

Details: `references/etoro-api.md` (endpoints, verified vs assumed fields) and
`references/model-notes.md` (model zoo, pins, resource numbers, upstream issues).

## Verification

```bash
python3 ${CLAWK_SKILL_DIR}/scripts/kronos_setup.py --check
python3 ${CLAWK_SKILL_DIR}/scripts/kronos_forecast.py --input prices.csv --horizon 5 --format json
python3 ${CLAWK_SKILL_DIR}/scripts/etoro_data.py check
python3 ${CLAWK_SKILL_DIR}/scripts/etoro_trade.py status
```

`--check` prints `"ok": true`; the forecast JSON has 5 `forecast` rows with numeric `close`,
`close_p10`, `close_p90` and a `disclaimer`; `check` prints `"ok": true` and the eToro username;
`status` prints the trading settings and today's remaining limits.
