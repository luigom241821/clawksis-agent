#!/usr/bin/env python3
"""eToro order placement for the Kronos skill: market buys by amount and position closes,
inside hard limits the user sets in config.yaml.

OFF BY DEFAULT. Every guard runs here, before any request leaves the machine:

- ``skills.config.kronos.trading.enabled`` must be true; an unreadable config.yaml means off.
- ``skills.config.kronos.trading.account`` picks ``demo`` (default) or ``real``.
- A buy is long-only and unleveraged (leverage 1, real-asset settlement), at most
  ``max_order_usd``; today's (UTC) opened total stays within ``max_daily_usd`` and
  ``max_orders_per_day``, counted from a local ledger under a file lock so two concurrent
  runs cannot both slip under the cap. A buy whose outcome is unknown (network failure)
  keeps counting until it is confirmed.
- A close only reduces risk, so it is not capped, but the position must exist in the
  configured account.

The trading client reaches exactly the routes in TRADE_ROUTES (open order, close position,
order lookup); reads (symbol search, portfolio) go through the read-only ``etoro_data``
client. Endpoint notes: references/etoro-api.md § Trading.

Usage:
  etoro_trade.py status
  etoro_trade.py positions [--format table|json]
  etoro_trade.py buy SYMBOL --amount USD --reason TEXT [--dry-run]
  etoro_trade.py close POSITION_ID [--units N] --reason TEXT [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping

_SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from _kronos_common import (
    UTC,
    SkillError,
    clawk_home,
    display_home,
    dump_json,
    kronos_home,
    render_table,
    run_cli,
)
from etoro_data import (
    BASE_URL,
    USER_AGENT,
    EtoroClient,
    EtoroError,
    _default_opener,
    _error_detail,
    _lookup_names,
    _retry_after,
    load_keys,
)

CONFIG_PATH = ("skills", "config", "kronos", "trading")
SET_CMD = "clawk config set skills.config.kronos.trading"
TRADE_ROUTES = (
    ("POST", re.compile(r"^/api/v2/trading/execution/(?:demo/)?orders$")),
    (
        "POST",
        re.compile(
            r"^/api/v1/trading/execution/(?:demo/)?market-open-orders/by-amount$"
        ),
    ),
    (
        "POST",
        re.compile(
            r"^/api/v1/trading/execution/(?:demo/)?market-close-orders/positions/\d+$"
        ),
    ),
    ("GET", re.compile(r"^/api/v2/trading/info/(?:demo/)?orders:lookup$")),
)
# v2 order lookup status ids (etoro-go); see references/etoro-api.md.
ORDER_STATUS = {
    1: "received",
    2: "placed",
    3: "filled",
    4: "rejected",
    5: "partially_filled",
    6: "pending_cancel",
    7: "canceled",
    8: "expired",
    9: "canceled_partially_filled",
    10: "rejected_partially_filled",
}
FINAL_STATUSES = {"filled", "rejected", "canceled", "expired", "partially_filled"}
# Statuses where no money moved: they do not count toward the daily limits.
NOT_COUNTED = {"rejected", "canceled", "expired", "dry_run"}
LOCK_TIMEOUT = 30.0
STALE_LOCK_SECONDS = 120.0
POLL_ATTEMPTS = 3
POLL_INTERVAL = 2.0
_HTTP_HINTS = {
    400: "eToro rejected the order (amount under the instrument minimum, market closed for "
    "this order type, or invalid parameters). Nothing was bought.",
    401: "eToro rejected the API keys.",
    403: "eToro refused: the key pair lacks trading permission, or its environment (real vs "
    "demo) does not match skills.config.kronos.trading.account.",
    404: "eToro has no such route or resource.",
    429: "eToro trading rate limit hit (about 20 orders per minute). Nothing was sent twice.",
}


class TradingRefused(SkillError):
    """A guard stopped the order before any request was made."""


# ── Config ──


@dataclass(frozen=True)
class TradingConfig:
    enabled: bool
    account: str
    max_order_usd: float
    max_daily_usd: float
    max_orders_per_day: int


DEFAULTS = TradingConfig(False, "demo", 100.0, 300.0, 5)


def _yaml_loader() -> tuple[Callable[[str], Any], type[Exception]]:
    """(safe loader, its parse-error class): ruamel.yaml (ships with Clawksis), else PyYAML."""
    try:
        from ruamel.yaml import YAML
        from ruamel.yaml.error import YAMLError
    except ImportError:
        try:
            import yaml
        except ImportError:
            raise TradingRefused(
                "Cannot read config.yaml (neither ruamel.yaml nor PyYAML is importable), "
                "so trading stays off.",
                hint="Run the script with the python3 that ships with Clawksis.",
            ) from None
        return yaml.safe_load, yaml.YAMLError
    return YAML(typ="safe").load, YAMLError


def _read_yaml(path: Path) -> Any:
    load, parse_error = _yaml_loader()
    try:
        return load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, parse_error) as exc:
        raise TradingRefused(
            f"config.yaml could not be read ({exc}); trading stays off."
        ) from None


def _as_bool(value: Any, key: str) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"true", "yes", "1", "on"}:
        return True
    if text in {"false", "no", "0", "off", "", "none"}:
        return False
    raise TradingRefused(f"skills.config.kronos.trading.{key} must be true or false.")


def _as_number(value: Any, key: str, kind: type) -> float | int:
    try:
        number = kind(float(str(value).strip()))
    except (TypeError, ValueError):
        number = None
    if number is None or number <= 0:
        raise TradingRefused(
            f"skills.config.kronos.trading.{key} must be a positive number."
        )
    return number


def _trading_section(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    node: Any = _read_yaml(path)
    for key in CONFIG_PATH:
        node = node.get(key) if isinstance(node, dict) else None
    return node if isinstance(node, dict) else {}


def load_trading_config(path: Path | None = None) -> TradingConfig:
    raw = _trading_section(path or clawk_home() / "config.yaml")
    account = str(raw.get("account") or DEFAULTS.account).strip().lower()
    if account not in {"demo", "real"}:
        raise TradingRefused(
            "skills.config.kronos.trading.account must be demo or real."
        )
    return TradingConfig(
        enabled=_as_bool(raw.get("enabled", DEFAULTS.enabled), "enabled"),
        account=account,
        max_order_usd=float(
            _as_number(
                raw.get("max_order_usd", DEFAULTS.max_order_usd), "max_order_usd", float
            )
        ),
        max_daily_usd=float(
            _as_number(
                raw.get("max_daily_usd", DEFAULTS.max_daily_usd), "max_daily_usd", float
            )
        ),
        max_orders_per_day=int(
            _as_number(
                raw.get("max_orders_per_day", DEFAULTS.max_orders_per_day),
                "max_orders_per_day",
                int,
            )
        ),
    )


def require_enabled(config: TradingConfig) -> None:
    if not config.enabled:
        raise TradingRefused(
            "Trading is turned off for this profile.",
            hint=f"Only the user turns it on: `{SET_CMD}.enabled true` (account "
            f"defaults to demo). Do not change trading settings on your own.",
        )


# ── Ledger (append-only JSONL; later lines with the same id update earlier ones) ──


def ledger_path() -> Path:
    return kronos_home() / "trades.jsonl"


class LedgerLock:
    """Cross-platform exclusive lock: an O_EXCL lock file, stale after STALE_LOCK_SECONDS."""

    def __init__(
        self,
        path: Path,
        *,
        timeout: float = LOCK_TIMEOUT,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.path, self.timeout, self._sleep, self._clock = path, timeout, sleep, clock

    def __enter__(self) -> LedgerLock:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        deadline = self._clock() + self.timeout
        while True:
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                if self._is_stale():
                    self.path.unlink(missing_ok=True)
                    continue
                if self._clock() >= deadline:
                    raise TradingRefused(
                        "Another order is still being placed; try again in a minute."
                    ) from None
                self._sleep(0.2)
                continue
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            return self

    def _is_stale(self) -> bool:
        try:
            return self._clock() - self.path.stat().st_mtime > STALE_LOCK_SECONDS
        except FileNotFoundError:
            return False

    def __exit__(self, *exc: object) -> None:
        self.path.unlink(missing_ok=True)


def read_ledger(path: Path | None = None) -> list[dict[str, Any]]:
    """Entries folded by id, in first-seen order; malformed lines are skipped."""
    path = path or ledger_path()
    if not path.exists():
        return []
    folded: dict[str, dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict) and row.get("id"):
            folded.setdefault(str(row["id"]), {}).update(row)
    return list(folded.values())


def append_ledger(row: Mapping[str, Any], path: Path | None = None) -> None:
    path = path or ledger_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(dict(row), ensure_ascii=False, default=str) + "\n")


def usage_today(
    entries: list[dict[str, Any]], account: str, now: datetime
) -> tuple[int, float]:
    """(orders opened, USD opened) today in UTC on *account*, excluding no-money outcomes."""
    today = now.astimezone(UTC).date().isoformat()
    opened = [
        e
        for e in entries
        if e.get("action") == "open"
        and e.get("account") == account
        and str(e.get("ts", "")).startswith(today)
        and e.get("status") not in NOT_COUNTED
    ]
    return len(opened), round(sum(float(e.get("amount") or 0.0) for e in opened), 2)


def check_limits(
    config: TradingConfig, amount: float, entries: list[dict[str, Any]], now: datetime
) -> dict[str, Any]:
    if amount <= 0:
        raise TradingRefused("The amount must be a positive number of USD.")
    if amount > config.max_order_usd:
        raise TradingRefused(
            f"{amount:.2f} USD is over the per-order limit of {config.max_order_usd:.2f} USD.",
            hint="Use a smaller amount. Only the user can raise the limit.",
        )
    count, spent = usage_today(entries, config.account, now)
    if count >= config.max_orders_per_day:
        raise TradingRefused(
            f"Today's limit of {config.max_orders_per_day} buys on the {config.account} "
            "account is used up.",
            hint="Limits reset at 00:00 UTC. Only the user can raise them.",
        )
    if spent + amount > config.max_daily_usd + 1e-9:
        left = max(config.max_daily_usd - spent, 0.0)
        raise TradingRefused(
            f"This buy would take today's total to {spent + amount:.2f} USD; the daily "
            f"limit is {config.max_daily_usd:.2f} USD ({left:.2f} USD left).",
            hint="Limits reset at 00:00 UTC. Only the user can raise them.",
        )
    return {
        "orders_today": count,
        "usd_today": spent,
        "usd_left_after": round(config.max_daily_usd - spent - amount, 2),
    }


# ── Trading client ──


def _segment(account: str) -> str:
    return "demo/" if account == "demo" else ""


class TradeClient:
    """Reaches only TRADE_ROUTES; *opener* and *sleep* are injectable for tests."""

    def __init__(
        self,
        api_key: str,
        user_key: str,
        *,
        base_url: str = BASE_URL,
        timeout: float = 30.0,
        opener: Callable[..., Any] | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._api_key, self._user_key = api_key, user_key
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._open = opener or _default_opener()
        self._sleep = sleep

    def build_request(
        self,
        method: str,
        path: str,
        *,
        body: Mapping[str, Any] | None = None,
        query: Mapping[str, Any] | None = None,
        request_id: str | None = None,
    ) -> urllib.request.Request:
        if not any(m == method and rx.match(path) for m, rx in TRADE_ROUTES):
            raise TradingRefused(
                f"Refusing {method} {path}: not a known trading route."
            )
        url = self._base_url + path
        if query:
            url += "?" + urllib.parse.urlencode(query)
        headers = {
            "x-api-key": self._api_key,
            "x-user-key": self._user_key,
            # Also the idempotency key: a retry with the same id cannot open a second order.
            "x-request-id": request_id or str(uuid.uuid4()),
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        }
        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(dict(body)).encode("utf-8")
        return urllib.request.Request(url, data=data, headers=headers, method=method)

    def send(self, method: str, path: str, **kwargs: Any) -> Any:
        request = self.build_request(method, path, **kwargs)
        for attempt in range(2):
            try:
                with self._open(request, timeout=self._timeout) as response:
                    raw = response.read()
                return json.loads(raw.decode("utf-8") or "null") if raw else None
            except urllib.error.HTTPError as exc:
                raw = exc.read() if exc.fp else b""
                if exc.code == 429 and attempt == 0:
                    self._sleep(
                        _retry_after(
                            exc.headers.get("Retry-After") if exc.headers else None
                        )
                    )
                    continue
                raise EtoroError(
                    f"HTTP {exc.code} from eToro: {_error_detail(raw) or 'no detail'}",
                    hint=_HTTP_HINTS.get(exc.code),
                    status=exc.code,
                ) from None
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                reason = getattr(exc, "reason", exc)
                raise EtoroError(f"No answer from eToro: {reason}") from None
            except ValueError as exc:
                raise EtoroError(f"eToro returned a non-JSON response: {exc}") from None
        raise EtoroError(
            "eToro rate limit persisted after one retry.",
            hint=_HTTP_HINTS[429],
            status=429,
        )

    def open_buy(
        self, account: str, instrument_id: int, amount: float, request_id: str
    ) -> tuple[Any, str]:
        """Market buy by amount; the v1 route only answers when the v2 route is missing."""
        seg = _segment(account)
        body = {
            "action": "open",
            "transaction": "buy",
            "instrumentId": instrument_id,
            "settlementType": "real",
            "orderType": "mkt",
            "leverage": 1,
            "amount": amount,
        }
        try:
            path = f"/api/v2/trading/execution/{seg}orders"
            return self.send("POST", path, body=body, request_id=request_id), "v2"
        except EtoroError as exc:
            if exc.status not in (404, 405):
                raise
        legacy = {
            "InstrumentID": instrument_id,
            "IsBuy": True,
            "Leverage": 1,
            "Amount": amount,
        }
        path = f"/api/v1/trading/execution/{seg}market-open-orders/by-amount"
        return self.send("POST", path, body=legacy, request_id=str(uuid.uuid4())), "v1"

    def close_position(
        self, account: str, position_id: int, instrument_id: int, units: float | None
    ) -> Any:
        path = (
            f"/api/v1/trading/execution/{_segment(account)}market-close-orders/"
            f"positions/{int(position_id)}"
        )
        body = {"InstrumentId": instrument_id, "UnitsToDeduct": units}
        return self.send("POST", path, body=body, request_id=str(uuid.uuid4()))

    def lookup(self, account: str, order_id: int) -> tuple[str, str | None]:
        """(status, error message) of an order; ``("submitted", None)`` when unknown."""
        try:
            payload = self.send(
                "GET",
                f"/api/v2/trading/info/{_segment(account)}orders:lookup",
                query={"orderId": int(order_id)},
            )
        except EtoroError:
            return "submitted", None
        status = payload.get("status") if isinstance(payload, dict) else None
        if not isinstance(status, dict):
            return "submitted", None
        try:
            name = ORDER_STATUS.get(int(status.get("id")), "submitted")
        except (TypeError, ValueError):
            name = "submitted"
        return name, status.get("errorMessage") or None


def order_id_of(payload: Any) -> int | None:
    if not isinstance(payload, dict):
        return None
    for value in (
        payload.get("orderId"),
        (payload.get("orderForOpen") or {}).get("orderID"),
        (payload.get("orderForClose") or {}).get("orderID"),
    ):
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return None


# ── Commands ──


@dataclass
class Deps:
    """Everything a command touches outside this module, injectable for tests."""

    config_path: Path | None = None
    ledger: Path | None = None
    now: Callable[[], datetime] = lambda: datetime.now(UTC)
    reader: EtoroClient | None = None
    trader: TradeClient | None = None
    sleep: Callable[[float], None] = time.sleep

    def clients(self) -> tuple[EtoroClient, TradeClient]:
        if self.reader is None or self.trader is None:
            keys = load_keys()
            self.reader = self.reader or EtoroClient(*keys)
            self.trader = self.trader or TradeClient(*keys)
        return self.reader, self.trader

    def lock(self) -> LedgerLock:
        target = self.ledger or ledger_path()
        return LedgerLock(target.with_suffix(".lock"), sleep=self.sleep)


def cmd_status(_args: argparse.Namespace, deps: Deps) -> dict[str, Any]:
    config = load_trading_config(deps.config_path)
    count, spent = usage_today(read_ledger(deps.ledger), config.account, deps.now())
    return {
        "ok": True,
        "config": asdict(config),
        "today_utc": {
            "buys": count,
            "usd": spent,
            "buys_left": max(config.max_orders_per_day - count, 0),
            "usd_left": round(max(config.max_daily_usd - spent, 0.0), 2),
        },
        "ledger": str(deps.ledger or ledger_path()),
        "change_settings": f"{SET_CMD}.<enabled|account|max_order_usd|max_daily_usd|"
        "max_orders_per_day> <value> (the user decides; config.yaml in "
        f"{display_home()})",
    }


def _position_row(pos: Mapping[str, Any], names: Mapping[int, Any]) -> dict[str, Any]:
    instrument_id = int(pos.get("instrumentID") or 0)
    info = names.get(instrument_id) or {}
    pnl = pos.get("unrealizedPnL")
    return {
        "position_id": pos.get("positionID"),
        "symbol": info.get("symbolFull"),
        "instrument_id": instrument_id,
        "direction": "long" if pos.get("isBuy", True) else "short",
        "units": pos.get("units"),
        "invested_usd": pos.get("amount"),
        "open_rate": pos.get("openRate"),
        "leverage": pos.get("leverage"),
        "unrealized_pnl": pnl.get("pnL") if isinstance(pnl, dict) else None,
    }


def cmd_positions(_args: argparse.Namespace, deps: Deps) -> dict[str, Any]:
    config = load_trading_config(deps.config_path)
    reader, _ = deps.clients()
    portfolio, _path = reader.portfolio(config.account)
    positions = [p for p in portfolio.get("positions") or [] if isinstance(p, dict)]
    ids = sorted({int(p.get("instrumentID") or 0) for p in positions} - {0})
    names, _failed = _lookup_names(reader, ids[:60])
    return {
        "ok": True,
        "account": config.account,
        "positions": [_position_row(p, names) for p in positions],
        "note": "Copy-trading positions are not listed: close them in the eToro app.",
    }


def _poll(trader: TradeClient, account: str, order_id: int, sleep: Callable) -> tuple:
    status, error = "submitted", None
    for _ in range(POLL_ATTEMPTS):
        sleep(POLL_INTERVAL)
        status, error = trader.lookup(account, order_id)
        if status in FINAL_STATUSES:
            break
    return status, error


def _submit_buy(
    deps: Deps, trader: TradeClient, entry: dict[str, Any]
) -> tuple[int | None, str]:
    """Send the order inside the lock; record the outcome before the lock is released."""
    try:
        payload, api = trader.open_buy(
            entry["account"], entry["instrument_id"], entry["amount"], entry["id"]
        )
    except EtoroError as exc:
        status = "rejected" if exc.status and 400 <= exc.status < 500 else "unknown"
        append_ledger(
            {"id": entry["id"], "status": status, "error": str(exc)}, deps.ledger
        )
        if status == "unknown":
            exc.hint = (
                "The order may or may not have reached eToro. Check `etoro_trade.py "
                "positions` before buying again; it counts toward today's limit until then."
            )
        raise
    order_id = order_id_of(payload)
    append_ledger(
        {"id": entry["id"], "status": "submitted", "order_id": order_id, "api": api},
        deps.ledger,
    )
    return order_id, api


def cmd_buy(args: argparse.Namespace, deps: Deps) -> dict[str, Any]:
    config = load_trading_config(deps.config_path)
    require_enabled(config)
    amount = round(float(args.amount), 2)
    check_limits(config, amount, read_ledger(deps.ledger), deps.now())
    reader, trader = deps.clients()
    instrument = reader.resolve(args.symbol)
    entry = {
        "id": str(uuid.uuid4()),
        "ts": deps.now().astimezone(UTC).isoformat(),
        "action": "open",
        "account": config.account,
        "symbol": instrument.get("internalSymbolFull") or args.symbol,
        "instrument_id": int(instrument["instrumentId"]),
        "amount": amount,
        "leverage": 1,
        "reason": args.reason,
    }
    if args.dry_run:
        return {"ok": True, "dry_run": True, "would_buy": entry}
    with deps.lock():
        limits = check_limits(config, amount, read_ledger(deps.ledger), deps.now())
        append_ledger({**entry, "status": "submitting"}, deps.ledger)
        order_id, api = _submit_buy(deps, trader, entry)
    status, error = "submitted", None
    if order_id is not None:
        status, error = _poll(trader, config.account, order_id, deps.sleep)
        append_ledger(
            {"id": entry["id"], "status": status, "error": error}, deps.ledger
        )
    return {
        "ok": status not in {"rejected", "canceled", "expired"},
        "order": {**entry, "order_id": order_id, "status": status, "api": api},
        "error": error,
        "limits": limits,
        "disclaimer": "Automated order inside the user's limits; not financial advice.",
    }


def _find_position(portfolio: Mapping[str, Any], position_id: int) -> dict[str, Any]:
    for pos in portfolio.get("positions") or []:
        if isinstance(pos, dict) and str(pos.get("positionID")) == str(position_id):
            return pos
    raise TradingRefused(
        f"No open position {position_id} in the account.",
        hint="List them with `etoro_trade.py positions`.",
    )


def cmd_close(args: argparse.Namespace, deps: Deps) -> dict[str, Any]:
    config = load_trading_config(deps.config_path)
    require_enabled(config)
    reader, trader = deps.clients()
    portfolio, _path = reader.portfolio(config.account)
    position = _find_position(portfolio, args.position_id)
    held = float(position.get("units") or 0.0)
    units = args.units
    if units is not None and not 0 < units <= held:
        raise TradingRefused(f"--units must be above 0 and at most {held}.")
    entry = {
        "id": str(uuid.uuid4()),
        "ts": deps.now().astimezone(UTC).isoformat(),
        "action": "close",
        "account": config.account,
        "position_id": int(args.position_id),
        "instrument_id": int(position.get("instrumentID") or 0),
        "units": units if units is not None else "all",
        "reason": args.reason,
    }
    if args.dry_run:
        return {"ok": True, "dry_run": True, "would_close": entry}
    with deps.lock():
        append_ledger({**entry, "status": "submitting"}, deps.ledger)
        try:
            payload = trader.close_position(
                config.account, entry["position_id"], entry["instrument_id"], units
            )
        except EtoroError as exc:
            append_ledger(
                {"id": entry["id"], "status": "failed", "error": str(exc)}, deps.ledger
            )
            raise
        order_id = order_id_of(payload)
        append_ledger(
            {"id": entry["id"], "status": "submitted", "order_id": order_id},
            deps.ledger,
        )
    return {
        "ok": True,
        "close": {**entry, "order_id": order_id, "status": "submitted"},
        "note": "eToro fills the close asynchronously; confirm with `etoro_trade.py positions`.",
    }


def _positions_table(result: dict[str, Any]) -> str:
    headers = [
        "position_id",
        "symbol",
        "direction",
        "units",
        "invested_usd",
        "unrealized_pnl",
    ]
    rows = [[row.get(h) for h in headers] for row in result["positions"]]
    return render_table(headers, rows) if rows else "No open positions."


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status", help="trading settings and today's usage (no network)")
    positions = sub.add_parser("positions", help="open positions with their ids")
    positions.add_argument("--format", choices=("json", "table"), default="table")
    buy = sub.add_parser("buy", help="market buy by USD amount (long, leverage 1)")
    buy.add_argument("symbol")
    buy.add_argument("--amount", type=float, required=True, help="USD to invest")
    buy.add_argument("--reason", required=True, help="why, for the trade log")
    buy.add_argument("--dry-run", action="store_true")
    close = sub.add_parser("close", help="close a position (all units unless --units)")
    close.add_argument("position_id", type=int)
    close.add_argument("--units", type=float, default=None)
    close.add_argument("--reason", required=True, help="why, for the trade log")
    close.add_argument("--dry-run", action="store_true")
    return parser


COMMANDS = {
    "status": cmd_status,
    "positions": cmd_positions,
    "buy": cmd_buy,
    "close": cmd_close,
}


def main(argv: list[str] | None = None, deps: Deps | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = COMMANDS[args.command](args, deps or Deps())
    if args.command == "positions" and args.format == "table":
        print(_positions_table(result))
    else:
        print(dump_json(result))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(run_cli(main))
