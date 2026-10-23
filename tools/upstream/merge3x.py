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
import json
from sync import ROOT, STATE_FILE, rebrand, show
from mkbase import unmap_path
from automerge import NOUS_ACTIVE

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
        check=False,
    )
    if res.returncode == 0 and res.stdout:
        return res.stdout.decode("utf-8")
    return text


def py_trivia_lines(text: str) -> set[int]:
    """Indices (0-based) de lineas que son comentario de linea completa o parte
    de un docstring. Se tratan como 'trivia': no participan del matching."""
    import io
    import tokenize

    out: set[int] = set()
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return out
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if (
            not isinstance(
                node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
            )
            or not body
        ):
            continue
        first = body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            start, end = first.lineno, first.end_lineno or first.lineno
            if not isinstance(node, ast.Module) and start == node.lineno:
                continue  # docstring en la misma linea que el def
            out.update(range(start - 1, end))
    try:
        for tok in tokenize.generate_tokens(io.StringIO(text).readline):
            if tok.type == tokenize.COMMENT and tok.line.lstrip().startswith("#"):
                out.add(tok.start[0] - 1)
    except (tokenize.TokenError, IndentationError, SyntaxError):
        pass
    return out


class Side:
    """Lineas 'clave' (no vacias y no trivia) + el bloque de trivia (blancos,
    comentarios, docstrings) que precede a cada una."""

    def __init__(self, text: str, trivia: bool = False):
        text = text.replace("\r\n", "\n")
        lines = text.split("\n")
        if lines and lines[-1] == "":
            lines.pop()
        triv = py_trivia_lines(text) if trivia else set()
        self.keys: list[str] = []
        self.lines: list[str] = []
        self.pre: list[list[str]] = []
        block: list[str] = []
        for idx, ln in enumerate(lines):
            ln = ln.rstrip()
            if not ln or idx in triv:
                block.append(ln)
                continue
            self.keys.append(ln)
            self.lines.append(ln)
            self.pre.append(block)
            block = []
        self.tail = block

    @staticmethod
    def _cap(block: list[str], cap: int | None) -> list[str]:
        if cap is None:
            return list(block)
        out: list[str] = []
        run = 0
        for ln in block:
            if ln == "":
                run += 1
                if run <= cap:
                    out.append(ln)
            else:
                run = 0
                out.append(ln)
        return out

    def emit(self, i: int, j: int, cap: int | None = None) -> list[str]:
        out: list[str] = []
        for k in range(i, j):
            out.extend(self._cap(self.pre[k], cap))
            out.append(self.lines[k])
        return out


def _tkey(block: list[str]) -> list[str]:
    return [ln.strip() for ln in block if ln.strip()]


def merge_trivia(b: list[str], a: list[str], t: list[str]) -> list[str]:
    """Trivia de una linea estable: si el fork no la toco -> upstream; si
    upstream no la toco -> fork; si ambos -> upstream."""
    kb, ka, kt = _tkey(b), _tkey(a), _tkey(t)
    if ka == kb or ka == kt:
        return t
    if kt == kb:
        return Side._cap(a, 2)
    return t


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


def merge_text(
    base_t: str, ours_t: str, theirs_t: str, trivia: bool = False
) -> tuple[str, int]:
    """Devuelve (texto_mergeado, n_conflictos)."""
    B, A, T = Side(base_t, trivia), Side(ours_t, trivia), Side(theirs_t, trivia)
    out: list[str] = []
    conflicts = 0
    iz = ia = ib = 0
    for zm, ze, am, ae, bm, be in sync_regions(B.keys, A.keys, T.keys):
        if (am - ia) or (bm - ib):
            a_chunk = A.keys[ia:am]
            b_chunk = T.keys[ib:bm]
            z_chunk = B.keys[iz:zm]
            if a_chunk == b_chunk or a_chunk == z_chunk:
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
            for k in range(ze - zm):
                out += merge_trivia(B.pre[zm + k], A.pre[am + k], T.pre[bm + k])
                out.append(T.lines[bm + k])
            iz, ia, ib = ze, ae, be
    out += merge_trivia(B.tail, A.tail, T.tail)
    text = "\n".join(out).strip("\n") + "\n"
    return text, conflicts


def compiles(text: str) -> bool:
    try:
        ast.parse(text)
        return True
    except (SyntaxError, ValueError):
        return False


def merge_file(
    fp: str,
    base_rev: str,
    ours_rev: str | None = None,
    target: str | None = None,
) -> tuple[str, str | None, int]:
    """-> (estado, texto, n_conflictos). estado in
    merged|conflict|nocompile|nous|skip.

    ours_rev: leer el lado fork de git (p.ej. el main previo al sync) en vez
    del working tree. target: generar el lado upstream rebrandeando ese
    tag/commit (rebrand actual) en vez de leer pending/<f>.theirs."""
    dest = ROOT / fp
    if target:
        up = unmap_path(fp)
        raw = show(target, up)
        theirs_b = rebrand(raw, up) if raw is not None else None
    else:
        theirs_f = PENDING / f"{fp.replace('/', '__')}.theirs"
        theirs_b = theirs_f.read_bytes() if theirs_f.exists() else None
    if ours_rev:
        ours_b = show(ours_rev, fp)
    else:
        ours_b = dest.read_bytes() if dest.is_file() else None
    if ours_b is None or theirs_b is None or not theirs_b.strip():
        return "skip", None, 0
    base_b = base_rebranded(fp, base_rev)
    if base_b is None:
        return "skip", None, 0
    try:
        base_t = base_b.decode("utf-8")
        ours_t = ours_b.decode("utf-8")
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
    text, n = merge_text(base_t, ours_t, theirs_t, trivia=is_py)
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
    ap.add_argument(
        "--base-map",
        help="TSV 'path<TAB>base_rev' para fijar la base por archivo",
    )
    ap.add_argument("--ours-rev", help="leer el lado fork de este rev de git")
    ap.add_argument(
        "--target", help="generar el lado upstream rebrandeando este tag/commit"
    )
    args = ap.parse_args()

    base_rev = merge_base()
    bmap: dict[str, str] = {}
    if args.base_map:
        for ln in Path(args.base_map).read_text(encoding="utf-8").splitlines():
            if "\t" in ln:
                k, v = ln.split("\t", 1)
                bmap[k.strip()] = v.strip()
    if args.file:
        st, text, n = merge_file(
            args.file, bmap.get(args.file, base_rev), args.ours_rev, args.target
        )
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
        st, text, n = merge_file(fp, bmap.get(fp, base_rev), args.ours_rev, args.target)
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
        (PENDING / f"MERGE3X_{names[k]}.txt").write_text("\n".join(v), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
