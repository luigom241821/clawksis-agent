---
name: kronos
description: Forecast stock/crypto prices; read eToro data and portfolio.
version: 0.1.0
author: samuelgradientai-sys, Clawksis
license: MIT
platforms: [linux, macos, windows]
metadata:
  clawk:
    tags: [Finance, Forecasting, Stocks, Crypto, eToro, Portfolio, Candlesticks, Time Series]
    category: finance
    related_skills: [stocks]
required_environment_variables:
  - name: ETORO_API_KEY
    prompt: eToro public API key (sent as x-api-key)
    help: "eToro > Settings > Trading > API Key Management. Only needed for eToro data; CSV files work without it."
    required_for: "eToro market data and portfolio (read-only)"
    optional: true
  - name: ETORO_USER_KEY
    prompt: eToro user key (sent as x-user-key; shown only once when created)
    help: "eToro > Settings > Trading > API Key Management. Only needed for eToro data; CSV files work without it."
    required_for: "eToro market data and portfolio (read-only)"
    optional: true
---

# Kronos Skill

Forecasts the next N candles (open/high/low/close/volume) of a stock, ETF, index or crypto
with the open-source Kronos foundation model, running locally on CPU, and pulls candles or
the user's open positions from eToro's Public API. eToro access is read-only: the client has
no order, close or edit endpoints. Kronos is a research model that often fails to beat
"repeat the last close", so every forecast ships with a backtest-based honesty check and a
not-financial-advice disclaimer; it is not a live-quote or fundamentals tool.

## When to Use

- "Forecast / predict AAPL for the next 10 days", "what might BTC do in the next 24 hours",
  "next candles for EURUSD", "chart a forecast band for my stock".
- Spanish triggers: "pronóstico de acciones", "predecir velas", "¿qué hará Tesla la próxima
  semana?", "proyección del bitcoin", "predicción del precio", "analizar mi portafolio de
  eToro", "conecta mi cuenta de eToro", "¿vale la pena este modelo para esta acción?".
- Reviewing an eToro portfolio: positions, weights, unrealized P&L, copy-trading, then
  forecasting the largest holdings.
- Judging whether a forecast model adds value for one instrument (walk-forward backtest).
- Not for: placing or changing trades (never possible here; the user trades in the eToro
  app), live quotes or company fundamentals (the optional `stocks` skill covers Yahoo data).

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

## Pitfalls

- **Not advice, and often no better than naive.** Independent tests (upstream issues #354,
  #375) found Kronos losing to "repeat the last close" and its sampled bands covering ~58% of
  outcomes instead of 90%. Never present a forecast without the backtest verdict.
- **Read-only eToro.** Requests to buy, sell, close or set stops: explain this skill cannot
  trade and point the user to the eToro app. Do not look for workarounds.
- **401/403 from eToro**: wrong key, a demo key used with `--account real` (or the reverse), or
  a key without that permission. `etoro_data.py check` shows the granted scopes.
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
```

`--check` prints `"ok": true`; the forecast JSON has 5 `forecast` rows with numeric `close`,
`close_p10`, `close_p90` and a `disclaimer`; `check` prints `"ok": true` and the eToro username.
