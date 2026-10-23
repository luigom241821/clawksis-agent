#!/usr/bin/env python3
"""Merge de 3 vias insensible a lineas en blanco, con marcadores de conflicto.

Variante de merge3.py pensada para el ruido que deja el squash inicial del
fork: lineas en blanco duplicadas (docstrings, bloques de imports) y el
reformateo masivo con ruff. `git merge-file` ve ese ruido como cambios y
genera conflictos falsos en casi todos los archivos.

Algoritmo (diff3 clasico, estilo bzr merge3):
  1. .py: los tres lados (base, fork, upstream) se formatean antes con
     `ruff format` (misma config del repo).
  2. Se comparan SOLO las lineas no vacias (sin trailing whitespace, con la
     indentacion intacta). Las lineas en blanco no participan del matching.
  3. Regiones estables y cambios de un solo lado se resuelven solos; en las
     regiones estables se emite el layout de upstream (sus lineas en blanco).
  4. Si ambos lados cambiaron la misma region distinto -> conflicto, con
     marcadores `<<<<<<< fork` / `||||||| base` / `=======` / `>>>>>>> upstream`.

Archivos sin conflicto que compilan (y sin acople Nous nuevo) se escriben con
--apply. Con --write-conflicts tambien se escriben los que tienen conflicto
(con marcadores) para resolverlos a mano.

Salidas en pending/: MERGE3X_APPLIED.txt, MERGE3X_CONFLICTS.txt,
MERGE3X_SKIPPED.txt, MERGE3X_NOCOMPILE.txt, MERGE3X_NOUS.txt.

Uso:
  python tools/upstream/merge3x.py --list lista.txt                # dry-run
  python tools/upstream/merge3x.py --list lista.txt --apply
  python tools/upstream/merge3x.py --list lista.txt --apply --write-conflicts
  python tools/upstream/merge3x.py --file ruta/al/archivo.py --stdout
"""

from __future__ import annotations

import argparse
import ast
import subprocess
import sys
from difflib import SequenceMatcher
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import json  # noqa: E402
from sync import ROOT, STATE_FILE, rebrand, show  # noqa: E402
from mkbase import unmap_path  # noqa: E402
from automerge import NOUS_ACTIVE  # noqa: E402

PENDING = HERE / "pending"

M_OURS = "<<<<<<< fork"
M_BASE = "||||||| base"
M_SEP = "======="
M_THEIRS = ">>>>>>> upstream"


def merge_base() -> str:
    st = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return st.get("merge_base_commit") or st["last_synced_commit"]


def base_rebranded(fork_path: str, base_rev: str) -> bytes | None:
    up = unmap_path(fork_path)
    b = show(base_rev, up)
    if b is None and up != fork_path:
        b = show(base_rev, fork_path)
    return rebrand(b, up) if b is not None else None


def ruff_canon(text: str) -> str:
    res = subprocess.run(
        ["ruff", "format", "--stdin-filename", "x.py", "-"],
        input=text.encode("utf-8"),
        cwd=ROOT,
        capture_output=True,
    )
    if res.returncode == 0 and res.stdout:
        return res.stdout.decode("utf-8")
    return text


class Side:
    """Lineas no vacias + cuantas lineas en blanco preceden a cada una."""

    def __init__(self, text: str):
        lines = text.replace("\r\n", "\n").split("\n")
        if lines and lines[-1] == "":
            lines.pop()
        self.keys: list[str] = []
        self.lines: list[str] = []
        self.blanks: list[int] = []
        pending = 0
        for ln in lines:
            ln = ln.rstrip()
            if not ln:
                pending += 1
                continue
            self.keys.append(ln)
            self.lines.append(ln)
            self.blanks.append(pending)
            pending = 0
        self.trailing_blanks = pending

    def emit(self, i: int, j: int, cap: int | None = None) -> list[str]:
        out: list[str] = []
        for k in range(i, j):
            n = self.blanks[k]
            if cap is not None:
                n = min(n, cap)
            out.extend([""] * n)
            out.append(self.lines[k])
        return out


def _intersect(ra: tuple[int, int], rb: tuple[int, int]) -> tuple[int, int] | None:
    sa = max(ra[0], rb[0])
    sb = min(ra[1], rb[1])
    return (sa, sb) if sa < sb else None


def sync_regions(base: list[str], a: list[str], b: list[str]):
    am = SequenceMatcher(None, base, a, autojunk=False).get_matching_blocks()
    bm = SequenceMatcher(None, base, b, autojunk=False).get_matching_blocks()
    ia = ib = 0
    out = []
    while ia < len(am) and ib < len(bm):
        abase, amatch, alen = am[ia]
        bbase, bmatch, blen = bm[ib]
        i = _intersect((abase, abase + alen), (bbase, bbase + blen))
        if i:
            intbase, intend = i
            intlen = intend - intbase
            asub = amatch + (intbase - abase)
            bsub = bmatch + (intbase - bbase)
            out.append((intbase, intend, asub, asub + intlen, bsub, bsub + intlen))
        if (abase + alen) < (bbase + blen):
            ia += 1
        else:
            ib += 1
    out.append((len(base), len(base), len(a), len(a), len(b), len(b)))
    return out


def merge_text(base_t: str, ours_t: str, theirs_t: str) -> tuple[str, int]:
    """Devuelve (texto_mergeado, n_conflictos)."""
    B, A, T = Side(base_t), Side(ours_t), Side(theirs_t)
    out: list[str] = []
    conflicts = 0
    iz = ia = ib = 0
    for zm, ze, am, ae, bm, be in sync_regions(B.keys, A.keys, T.keys):
        if (am - ia) or (bm - ib):
            a_chunk = A.keys[ia:am]
            b_chunk = T.keys[ib:bm]
            z_chunk = B.keys[iz:zm]
            if a_chunk == b_chunk:
                out += T.emit(ib, bm)
            elif a_chunk == z_chunk:
                out += T.emit(ib, bm)
            elif b_chunk == z_chunk:
                out += A.emit(ia, am, cap=2)
            else:
                # recortar prefijo/sufijo comun entre fork y upstream
                p = 0
                while (
                    p < len(a_chunk) and p < len(b_chunk) and a_chunk[p] == b_chunk[p]
                ):
                    p += 1
                s = 0
                while (
                    s < len(a_chunk) - p
                    and s < len(b_chunk) - p
                    and a_chunk[-1 - s] == b_chunk[-1 - s]
                ):
                    s += 1
                out += T.emit(ib, ib + p)
                conflicts += 1
                out.append(M_OURS)
                out += A.emit(ia + p, am - s, cap=1)
                out.append(M_BASE)
                out += B.emit(iz, zm, cap=1)
                out.append(M_SEP)
                out += T.emit(ib + p, bm - s)
                out.append(M_THEIRS)
                out += T.emit(bm - s, bm)
            ia, ib = am, bm
        iz = zm
        if ze - zm > 0:
            out += T.emit(bm, be)
            iz, ia, ib = ze, ae, be
    text = "\n".join(out).lstrip("\n") + "\n"
    return text, conflicts


def compiles(text: str) -> bool:
    try:
        ast.parse(text)
        return True
    except (SyntaxError, ValueError):
        return False


def merge_file(fp: str, base_rev: str) -> tuple[str, str | None, int]:
    """-> (estado, texto, n_conflictos). estado in
    merged|conflict|nocompile|nous|skip."""
    dest = ROOT / fp
    theirs_f = PENDING / f"{fp.replace('/', '__')}.theirs"
    if not dest.is_file() or not theirs_f.exists():
        return "skip", None, 0
    theirs_b = theirs_f.read_bytes()
    if not theirs_b.strip():
        return "skip", None, 0
    base_b = base_rebranded(fp, base_rev)
    if base_b is None:
        return "skip", None, 0
    try:
        base_t = base_b.decode("utf-8")
        ours_t = dest.read_bytes().decode("utf-8")
        theirs_t = theirs_b.decode("utf-8")
    except UnicodeDecodeError:
        return "skip", None, 0
    is_py = fp.endswith(".py")
    if is_py:
        base_t, ours_t, theirs_t = (
            ruff_canon(base_t),
            ruff_canon(ours_t),
            ruff_canon(theirs_t),
        )
    text, n = merge_text(base_t, ours_t, theirs_t)
    if n:
        return "conflict", text, n
    if is_py:
        if not compiles(text):
            return "nocompile", text, 0
        text = ruff_canon(text)
    if NOUS_ACTIVE.search(text) and not NOUS_ACTIVE.search(ours_t):
        return "nous", text, 0
    return "merged", text, 0


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--list")
    g.add_argument("--file")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--write-conflicts", action="store_true")
    ap.add_argument("--stdout", action="store_true")
    args = ap.parse_args()

    base_rev = merge_base()
    if args.file:
        st, text, n = merge_file(args.file, base_rev)
        print(f"[merge3x] {args.file}: {st} ({n} conflictos)", file=sys.stderr)
        if args.stdout and text is not None:
            sys.stdout.write(text)
        return 0

    files = [
        ln.strip()
        for ln in Path(args.list).read_text(encoding="utf-8").splitlines()
        if ln.strip()
    ]
    buckets: dict[str, list[str]] = {
        k: [] for k in ("merged", "conflict", "nocompile", "nous", "skip")
    }
    for fp in files:
        st, text, n = merge_file(fp, base_rev)
        buckets[st].append(fp if st != "conflict" else f"{fp}\t{n}")
        if text is None:
            continue
        if args.apply and (
            st == "merged" or (st == "conflict" and args.write_conflicts)
        ):
            (ROOT / fp).write_text(text, encoding="utf-8")

    mode = "APLICADO" if args.apply else "DRY-RUN"
    print(f"=== merge3x [{mode}] sobre {len(files)} archivos ===")
    print(f"  merge limpio: {len(buckets['merged'])}")
    print(f"  con conflictos: {len(buckets['conflict'])}")
    print(f"  merge no compila: {len(buckets['nocompile'])}")
    print(f"  guard Nous: {len(buckets['nous'])}")
    print(f"  saltados (movido/irreconstruible): {len(buckets['skip'])}")
    names = {
        "merged": "APPLIED",
        "conflict": "CONFLICTS",
        "nocompile": "NOCOMPILE",
        "nous": "NOUS",
        "skip": "SKIPPED",
    }
    for k, v in buckets.items():
        (PENDING / f"MERGE3X_{names[k]}.txt").write_text(
            "\n".join(v), encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
