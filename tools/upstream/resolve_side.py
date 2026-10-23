#!/usr/bin/env python3
"""Resuelve marcadores de conflicto de merge3x eligiendo un lado por bloque.

Pensado para archivos donde la eleccion por lado es segura (tests, docs,
locales). Para cada bloque `<<<<<<< fork / ||||||| base / ======= / >>>>>>> upstream`:

  - si fork y upstream son iguales (ignorando blancos/espacios) -> upstream
  - --prefer theirs: upstream, salvo
      * --respect-fork-deletions y el lado fork esta vacio (el fork borro el
        bloque a proposito) -> fork
      * --nous-guard y el bloque de upstream menciona Nous Portal/billing ->
        fork (el fork no usa Nous)
  - --prefer ours: fork
  - --only-identical: solo resuelve los bloques con fork == upstream

Uso:
  python tools/upstream/resolve_side.py --prefer theirs [--respect-fork-deletions]
      [--nous-guard] [--dry-run] archivo...
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

M_OURS = "<<<<<<< fork"
M_BASE = "||||||| base"
M_SEP = "======="
M_THEIRS = ">>>>>>> upstream"

NOUS_TEXT = re.compile(
    r"nous[ _-]?portal|nous_subscription|nous[ _-]?billing|nousresearch\.com/|"
    r"portal\.nousresearch|nous_auth|_nous_|NOUS_|provider=.?nous|\"nous\"|'nous'",
    re.IGNORECASE,
)


def _key(lines: list[str]) -> list[str]:
    return [ln.strip() for ln in lines if ln.strip()]


def resolve(
    text: str, prefer: str, respect_del: bool, nous_guard: bool, only_ident=False
):
    out: list[str] = []
    stats = {"theirs": 0, "ours": 0}
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        if lines[i] != M_OURS:
            out.append(lines[i])
            i += 1
            continue
        j = i + 1
        ours: list[str] = []
        while lines[j] != M_BASE:
            ours.append(lines[j])
            j += 1
        j += 1
        while lines[j] != M_SEP:
            j += 1
        j += 1
        theirs: list[str] = []
        while lines[j] != M_THEIRS:
            theirs.append(lines[j])
            j += 1
        block = lines[i : j + 1]
        i = j + 1
        if only_ident and _key(ours) != _key(theirs):
            out.extend(block)
            continue
        pick = prefer
        if _key(ours) == _key(theirs):
            pick = "theirs"
        elif prefer == "theirs":
            if respect_del and not _key(ours):
                pick = "ours"
            elif (
                nous_guard
                and NOUS_TEXT.search("\n".join(theirs))
                and not NOUS_TEXT.search("\n".join(ours))
            ):
                pick = "ours"
        stats[pick] += 1
        out.extend(theirs if pick == "theirs" else ours)
    return "\n".join(out), stats


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prefer", choices=["theirs", "ours"], required=True)
    ap.add_argument("--respect-fork-deletions", action="store_true")
    ap.add_argument("--nous-guard", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument(
        "--only-identical",
        action="store_true",
        help="solo resolver bloques con fork == upstream; deja el resto",
    )
    ap.add_argument("files", nargs="+")
    args = ap.parse_args()
    tot = {"theirs": 0, "ours": 0}
    for f in args.files:
        p = Path(f)
        text = p.read_text(encoding="utf-8")
        if M_OURS not in text:
            continue
        new, st = resolve(
            text,
            args.prefer,
            args.respect_fork_deletions,
            args.nous_guard,
            args.only_identical,
        )
        for k in tot:
            tot[k] += st[k]
        if not args.dry_run:
            p.write_text(new, encoding="utf-8")
    print(f"[resolve_side] {len(args.files)} archivos: {tot}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
