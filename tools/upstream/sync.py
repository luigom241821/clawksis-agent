#!/usr/bin/env python3
"""Sync curado de cambios desde upstream (NousResearch/hermes-agent).

El fork NO comparte historia de git con upstream (la historia se recreo en el
squash inicial del 2026-06-04) y el arbol difiere por el rebrand
hermes->clawksis, por line endings (CRLF vs LF) y por espaciado inconsistente
heredado del squash. Por eso este sync no usa merge/cherry-pick/patch:
trabaja ARCHIVO POR ARCHIVO comparando contenido normalizado.

Para cada archivo que upstream cambio entre `last_synced_commit` y el target:

  estado del archivo en el fork                         accion
  ----------------------------------------------------  ----------------------
  igual al baseline upstream (modulo rebrand/espaciado)  reemplazar por la
                                                         version target
                                                         rebrandeada
  ya igual al target                                     nada
  divergente (cambios propios del fork)                  va a pending/ para
                                                         merge manual
  inexistente en el fork y upstream lo agrega            crear rebrandeado

Uso:
  python tools/upstream/sync.py                        # dry-run vs ultimo release
  python tools/upstream/sync.py --target v2026.6.5     # dry-run vs tag
  python tools/upstream/sync.py --target v2026.6.5 --apply

Despues de un --apply: revisar `git status`, resolver lo que quedo en
tools/upstream/pending/ (si hay), correr smoke tests, commitear. El estado
queda registrado en tools/upstream/sync_state.json.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
STATE_FILE = HERE / "sync_state.json"
PENDING_DIR = HERE / "pending"

UPSTREAM_URL = "https://github.com/NousResearch/hermes-agent.git"

# Renombres de paths del rebrand original (upstream -> fork): reemplazos
# ordenados sobre el path completo (el rebrand real renombro tambien archivos
# de docs/tests, ej. use-mcp-with-hermes.md -> use-mcp-with-clawk.md).
PATH_MAP = [
    ("hermes_cli", "clawk_cli"),
    ("hermes_bootstrap", "clawk_bootstrap"),
    ("hermes_constants", "clawk_constants"),
    ("hermes_logging", "clawk_logging"),
    ("hermes_state", "clawk_state"),
    ("hermes_time", "clawk_time"),
    ("hermes-agent", "clawksis-agent"),
    ("hermes-webhook", "clawk-webhook"),
    ("hermes-web", "clawksis-web"),
    ("hermes-acp", "clawk-acp"),
    ("hermes-dashboard", "clawksis-dashboard"),
    ("hermes", "clawk"),
    ("Hermes", "Clawksis"),
]

# Reemplazos de contenido en el MISMO orden que tools/rebrand.sh del monorepo
# (mas especifico primero). El orden importa: reproduce el transform historico
# tal cual se aplico al fork, incluidas sus redundancias.
_RAW = (
    "https://raw.githubusercontent.com/samuelgradientai-sys/clawksis-agent/main/scripts"
)
_PAGES = "https://samuelgradientai-sys.github.io/clawksis-agent"
CONTENT_MAP = [
    # URLs del sitio de upstream -> equivalentes del fork (instalador en GitHub
    # raw, docs en el GitHub Pages del fork). Van primero: el blanket
    # hermes-agent -> clawksis-agent las dejaria en un host inexistente.
    ("https://hermes-agent.nousresearch.com/install.sh", f"{_RAW}/install.sh"),
    ("https://hermes-agent.nousresearch.com/install.ps1", f"{_RAW}/install.ps1"),
    ("https://hermes-agent.nousresearch.com/install.cmd", f"{_RAW}/install.cmd"),
    # La pagina de producto del desktop no tiene equivalente en el fork: la raiz del repo.
    (
        "https://hermes-agent.nousresearch.com/desktop",
        "https://github.com/samuelgradientai-sys/clawksis-agent/",
    ),
    ("https://hermes-agent.nousresearch.com/docs/", f"{_PAGES}/"),
    ("https://hermes-agent.nousresearch.com/docs", _PAGES),
    (
        "https://hermes-agent.nousresearch.com/",
        "https://github.com/samuelgradientai-sys/clawksis-agent/",
    ),
    (
        "https://hermes-agent.nousresearch.com",
        "https://github.com/samuelgradientai-sys/clawksis-agent",
    ),
    ("NousResearch/hermes-agent", "samuelgradientai-sys/clawksis-agent"),
    ("hermes_cli", "clawk_cli"),
    ("hermes_bootstrap", "clawk_bootstrap"),
    ("hermes_constants", "clawk_constants"),
    ("hermes_logging", "clawk_logging"),
    ("hermes_state", "clawk_state"),
    ("hermes_time", "clawk_time"),
    ("hermes-agent", "clawksis-agent"),
    # El toolset de plataforma ``hermes-webhook`` es ``clawk-webhook`` como todos los
    # ``clawk-<plataforma>`` (el codigo los reconoce por el prefijo ``clawk-``); sin esta
    # entrada el ``hermes-web`` historico lo dejaba en ``clawksis-webhook``.
    ("hermes-webhook", "clawk-webhook"),
    ("hermes-web", "clawksis-web"),
    ("hermes-acp", "clawk-acp"),
    ("hermes-dashboard", "clawksis-dashboard"),
    ("HERMES_HOME", "CLAWK_HOME"),
    ("HERMES_INSTALL_DIR", "CLAWK_INSTALL_DIR"),
    ("HERMES_TUI_DIR", "CLAWK_TUI_DIR"),
    ("HERMES_WEB_DIST", "CLAWK_WEB_DIST"),
    ("HERMES_UID", "CLAWK_UID"),
    ("HERMES_GID", "CLAWK_GID"),
    ("HERMES_GIT_BASH_PATH", "CLAWK_GIT_BASH_PATH"),
    ("/opt/hermes", "/opt/clawksis"),
    ("~/.hermes", "~/.clawksis"),
    ("LocalAppData\\hermes", "LocalAppData\\clawksis"),
    ("LocalAppData/hermes", "LocalAppData/clawksis"),
    ("container_name: hermes", "container_name: clawksis"),
    ("--hermes-home", "--clawk-home"),
    ("HermesHome", "ClawkHome"),
    ("Hermes Agent", "Clawksis"),
    ("Hermes-Agent", "Clawksis"),
    ("<title>Hermes</title>", "<title>Clawksis</title>"),
    ('"Hermes"', '"Clawksis"'),
    ("'Hermes'", "'Clawksis'"),
    ("hermes setup", "clawk setup"),
    ("hermes chat", "clawk chat"),
    ("hermes gateway", "clawk gateway"),
    ("hermes update", "clawk update"),
    ("hermes config", "clawk config"),
    ("hermes dashboard", "clawk dashboard"),
    ("hermes model", "clawk model"),
    ("hermes doctor", "clawk doctor"),
    ("$ hermes", "$ clawk"),
    ('"hermes"', '"clawk"'),
    ('hermes = "hermes_cli.main:main"', 'clawk = "clawk_cli.main:main"'),
    ('hermes = "clawk_cli.main:main"', 'clawk = "clawk_cli.main:main"'),
    ('hermes-agent = "run_agent:main"', 'clawk-agent = "run_agent:main"'),
    ('hermes-acp = "acp_adapter.entry:main"', 'clawk-acp = "acp_adapter.entry:main"'),
    # Fallbacks blanket: el rebrand historico del fork reemplazo tambien las
    # menciones a secas (verificado contra el arbol real: class ClawksisACPAgent,
    # CLAWK_ALLOW_PRIVATE_URLS, docs "run Clawksis", etc.).
    # Simbolo de marca: el fork reemplazo el caduceo de Hermes (⚕, y ☤ desde
    # v0.2x) por la nabla de Gradient AI en todo el proyecto.
    ("⚕\ufe0f", "∇"),
    ("☤\ufe0f", "∇"),
    ("⚕", "∇"),
    ("☤", "∇"),
    # Esquema de Authorization ``HermesRoom`` (se compara en minusculas): la forma
    # minuscula tiene que seguir a ``ClawksisRoom``, no quedar en ``clawkroom``.
    ("hermesroom", "clawksisroom"),
    ("HERMES_", "CLAWK_"),
    ("HERMES", "CLAWKSIS"),
    ("Hermes", "Clawksis"),
    ("hermes", "clawk"),
]

# IDs de modelo de Nous (Hermes-3 / Hermes-4 y sus variantes, incluidos los
# slugs de OpenRouter ``nousresearch/hermes-*``). El blanket hermes->clawk de
# arriba los corrompe a ``clawk-3``/``clawk-4``, que NO existen en ningun
# proveedor y fallan en runtime. Se preservan haciendo stash/unstash alrededor
# del CONTENT_MAP (ver ``rebrand``). "Hermes" como producto/agente SI se
# rebrandea; solo los nombres de modelo Herme quedan intactos.
_MODEL_ID_RE = re.compile(
    r"(?:nousresearch/)?[Hh]ermes[ _-]?[34][\w.\-]*"
    # Mirror content-addressed (sha256) de binarios de terceros (uv, git...) que
    # usa el instalador: es un host real de Nous, verificado por hash. NO
    # confundir con los releases de Hermes (source_releases.py), que el fork no
    # debe descargar.
    r"|https://hermes-assets\.nousresearch\.com/upstream/[\w/.\-]*"
    # Imagen publica de sandbox (computer use) de upstream en Docker Hub: el
    # fork la usa tal cual (no publica una propia).
    r"|nousresearch/hermes-sandbox"
    # Paquetes npm del motor JS "Hermes" de Meta (hermes-parser, hermes-estree),
    # dependencias transitivas de babel/react-compiler: no son la marca.
    r"|\bhermes-(?:parser|estree|eslint|transform)\b"
)

# Carpeta HOME del usuario: en el fork es ``~/.clawksis``. El blanket
# hermes->clawk de CONTENT_MAP la convertiria en ``.clawk`` (que si es el nombre
# correcto para la config LOCAL de un proyecto: ``<repo>/.clawk/skills``,
# ``<repo>/.clawk/bin``, ``environment.json``, ``plans``, ``.clawk.md``). Estas reglas
# detectan los contextos de HOME y los mapean a ``.clawksis`` antes del blanket.
#
# ``home_fix(text, old, new)`` es parametrico en el nombre de origen: el sync lo
# aplica a upstream con ``old=".hermes"``, y las mismas reglas aplicadas al arbol con
# ``old=".clawk"`` muestran donde el arbol quedo incoherente con ellas. En los patrones,
# ``{old}`` es el nombre (regex-escapado) y ``{brand}`` la marca sin punto (``hermes``).
_HOME_CTX = [
    # Filtro de entradas del PATH: `for p in os.get_exec_path() if ".hermes" not in
    # Path(p).parts` saca el store de herramientas de PM (~/.hermes/tools/...).
    r"(\bget_exec_path\(\)[^\n]*?)([\"']){old}\2",
    # process.env.HOME || '~', '.hermes'
    r"(process\.env\.HOME[^,;\n]{0,20},\s*)([\"']){old}\2",
    # $HOME/.hermes, ${HOME}/.hermes, ${HERMES_HOME:-$HOME/.hermes}, $HOME/.hermes${suffix},
    # %USERPROFILE%\.hermes, ${USERPROFILE}/.hermes, $env:USERPROFILE '.hermes, y el
    # especificador de systemd %h/.hermes (EnvironmentFile=%h/.hermes/.env).
    r"((?:\$\{?HOME\}?|%USERPROFILE%|\$\{?USERPROFILE\}?|\$env:USERPROFILE|%h)[/\\\s']+)(){old}",
    # Raices de HOME absolutas: /root/.hermes, /home/<user>/.hermes (tambien el placeholder
    # /home/<user>), /Users/<user>/.hermes, el stateDir de NixOS /var/lib/hermes/.hermes, el
    # volumen de Docker /opt/data/.hermes y /data/.hermes, y el placeholder /your/.hermes.
    r"((?<![\w.-])(?:/root|/home/[\w.<>-]+|/Users/[\w.<>-]+|/var/lib/{brand}|/opt/data|/data|/your)/)(){old}",
    # Lo mismo SIN barra inicial: miembros de tar (``"root/.hermes/skills/x"``,
    # ``home/<user>/.hermes``) y rutas de sandbox (``.../<task>/home/.hermes/...``).
    r"((?<![\w.<-])(?:root|home|home/[\w.<>-]+|Users/[\w.<>-]+)/)(){old}",
    # Prosa con un HOME nombrado: <scratch>/.hermes, stateDir/.hermes, tmp_path/.hermes,
    # Path.home()/.hermes, "remote .hermes/" (el HOME del sandbox remoto), y <root>/.hermes
    # salvo <root>/.hermes/{bin,skills} (el checkout: launchers y skills del proyecto).
    r"((?<![\w.-])(?:<(?:scratch|home)>|stateDir|tmp_path|Path\.home\(\))/)(){old}",
    r"((?<![\w.-])<root>/)(){old}(?!/(?:bin|skills)\b)",
    r"(\bremote\s+(?:``)?)(){old}",
    # f-strings / templates cuyo placeholder nombra un home: f"{self._remote_home}/.hermes",
    # `${fakeHome}/.hermes`, "${config.home.homeDirectory}/.hermes", f"{home}/.hermes".
    r"(\{[^{}\n]*[Hh][Oo][Mm][Ee][^{}\n]*\}/)(){old}",
    # Regex con el punto escapado: r'\$HOME/\.hermes/\.env', r'\~/\.hermes/', r'~\/\.hermes/',
    # r'(?:\$home|\$\{home\})/\.hermes/' (approval_detection, skills_guard).
    r"((?:~|\$\{?[Hh][Oo][Mm][Ee]\\?\}?\)?|\b[Hh][Oo][Mm][Ee]\\\}\))\\?/\\)(){old}",
    # Un literal ``".hermes"`` en una linea que habla de perfiles: los perfiles solo viven en
    # el HOME (``parts[-3] == ".hermes" and parts[-2] == "profiles"``).
    r"()([\"']){old}\2(?=[^\n]*\bprofiles\b)",
    # Prosa relativa con una subcarpeta que solo existe en el HOME: ``@file:.hermes/.env``,
    # ``.hermes/auth.json``, ``exist in .hermes/sessions``. (``config.yaml``/``SOUL.md``/
    # ``skills`` existen tambien en la carpeta local de un proyecto: no cuentan.)
    r"((?<![\w./-]))(){old}(?=/(?:sessions|profiles|logs|state\.db|auth\.json"
    r"|\.anthropic_oauth\.json|mcp-tokens|\.env)(?![\w-]))",
]

# Fin del nombre: ``.hermes`` seguido de un separador (``/``, comilla, ``}``, ``$``, fin de
# oracion...), nunca ``.hermes-update-in-progress``, ``.hermes_sync``, ``.hermes.md``.
_HOME_END = r"(?![\w-])(?!\.\w)"

# Componentes de la carpeta LOCAL de un proyecto (``<repo>/.clawk/bin``,
# ``<repo>/.clawk/environment.json``, ``.clawk/plans``, adjuntos del desktop); no cuentan
# si el operando nombra un home (``REAL_HOME / ".hermes" / "bin"``, el uv del instalador).
_PROJECT_SUBDIRS = frozenset(
    {"bin", "environment.json", "plans", "attachments", "desktop-attachments"}
)
# Los plugins de proyecto del fork viven en ``./.clawksis/plugins`` (clawk_cli/plugins.py,
# plugins/memory/__init__.py): ``.hermes`` seguido de ``plugins`` es ``.clawksis`` tambien
# en un proyecto. Las demas carpetas locales de un proyecto siguen siendo ``.clawk/``.
_PLUGINS_DIR = "plugins"
# Componentes que solo existen en el HOME: ``root / ".hermes/logs/..."`` es el HOME aunque
# ``root`` suela nombrar un checkout.
_HOME_SUBDIRS = frozenset(
    {
        "profiles",
        "sessions",
        "logs",
        "state.db",
        "auth.json",
        "mcp-tokens",
        ".env",
        "cache",
    }
)
# Ultimo atomo del operando izquierdo que nombra la raiz de un proyecto, checkout o
# instalacion (``repo / ".hermes" / "skills"``, ``root / ".hermes" / "bin"``), no un HOME.
_PROJECT_OPERAND_RE = re.compile(
    r"(?i)^(?:repo\w*|r|work|workspace\w*|worktree\w*|proj\w*|install\w*|checkout\w*"
    r"|core|path|cwd|root|src|source\w*|update_?root)$"
)
# Lo mismo para un segmento literal (``tmp_path / "proj" / ".hermes"``); ``"root"`` no
# cuenta: ``tmp_path / "root" / ".hermes"`` imita ``/root/.hermes``.
_PROJECT_LITERAL_RE = re.compile(
    r"(?i)^(?:repo\w*|proj\w*|workspace\w*|worktree\w*|checkout\w*|src)$"
)
# ``<operando> / ".hermes"`` (Python/pathlib), tambien ``/ (".hermes" + suffix)`` y
# ``/ ("x" if c else ".hermes")``; el literal puede traer subruta (``".hermes/logs"``).
_JOIN_RE = re.compile(
    r"(\s*/\s*(?:\(\s*|\([^()\n]*?\belse\s+)?)([\"']){old}(?=(?:/[^\"'\n]*)?\2)"
)
# join(A, ".hermes", ...) / os.path.join / path.join / Path(A, ".hermes") / X.join(".hermes")
# / X.joinpath(".hermes") / PurePosixPath(".hermes", ...) / Path(".hermes") / "x"
_CALL_RE = re.compile(
    r"\b(?P<fn>[A-Za-z_][\w.]*)\(\s*"
    r"(?P<args>(?:[^()\"'\n]|\([^()\n]*\)|\"[^\"\n]*\"|'[^'\n]*')*?)"
    r"(?P<q>[\"']){old}(?=(?:/[^\"'\n]*)?(?P=q))"
)
_CALL_FNS = frozenset(
    {"join", "joinpath", "Path", "PurePath", "PurePosixPath", "PureWindowsPath"}
)
_NEXT_RE = re.compile(
    r"[\"']\s*(?:/\s*|,\s*|\)\s*/\s*|\)\s*\.join(?:path)?\(\s*)[\"']([\w.-]+)"
)
_CLOSERS = {")": "(", "]": "["}


def _next_component(text: str, pos: int) -> str | None:
    """Componente que sigue al nombre en ``pos``: ``/logs`` dentro del literal, o el
    literal siguiente (``/ "bin"``, ``, "bin"``, ``) / "bin"``, ``).join("bin")``)."""
    if text.startswith("/", pos):
        m = re.match(r"/([\w.-]+)", text[pos:])
        return m.group(1) if m else None
    m = _NEXT_RE.match(text, pos)
    return m.group(1) if m else None


def _primaries_before(text: str, end: int) -> list[str]:
    """Primarios (nombres, llamadas, subscripts, literales) encadenados con ``/`` que
    terminan en ``end``, del mas cercano al mas lejano. Best effort, una sola linea."""
    out: list[str] = []
    i = end
    while True:
        while i > 0 and text[i - 1] in " \t":
            i -= 1
        start = i
        while i > 0:
            ch = text[i - 1]
            if ch in _CLOSERS:
                depth, k = 0, i - 1
                while k >= 0 and text[k] != "\n":
                    depth += {ch: 1, _CLOSERS[ch]: -1}.get(text[k], 0)
                    if depth == 0:
                        break
                    k -= 1
                if k < 0 or text[k] == "\n":
                    break
                i = k
            elif ch in "\"'":
                j = text.rfind(ch, 0, i - 1)
                if j < 0 or "\n" in text[j:i]:
                    break
                i = j
            elif ch.isalnum() or ch in "_.":
                i -= 1
            else:
                break
        if i == start:
            return out
        out.append(text[i:start])
        k = i
        while k > 0 and text[k - 1] in " \t":
            k -= 1
        # ``a / b`` sigue la cadena; ``a // b`` o ``*/`` no son uniones de rutas.
        if k > 1 and text[k - 1] == "/" and text[k - 2] not in "/*":
            i = k - 1
            continue
        return out


def _primary_name(p: str) -> str:
    """Nombre que identifica un primario: ``state["root"]`` -> root, ``self.install`` ->
    install, ``Path(gateway.PROJECT_ROOT).resolve()`` -> PROJECT_ROOT, ``x.parent`` -> x."""
    prev = None
    while prev != p:
        prev = p
        p = re.sub(r"\.(?:resolve|absolute|expanduser|parent)(?:\(\))?$", "", p)
    m = re.search(r"\[\s*[\"']([\w-]+)[\"']\s*\]$", p)
    if m:
        return m.group(1)
    m = re.match(
        r"^(?:[\w.]*\.)?(?:Path|PurePath|PurePosixPath|str|fspath)\((.*)\)$", p
    )
    if m:
        return _primary_name(m.group(1).split(",")[-1].strip())
    m = re.search(r"([A-Za-z_]\w*)(?:\([^()]*\))?$", p)
    return m.group(1) if m else ""


def _home_operand(
    primaries: list[str], nxt: str | None, home_hint: bool = False
) -> bool:
    """¿El operando (primarios, del mas cercano al mas lejano) y la componente siguiente
    nombran un HOME? Por defecto si; no cuando nombran un proyecto/checkout/instalacion.
    ``home_hint``: la linea asigna ``HERMES_HOME`` (``"HERMES_HOME": str(Path(work) /
    ".hermes")``) o una variable con ``home`` en el nombre."""
    if nxt == _PLUGINS_DIR or nxt in _HOME_SUBDIRS:
        return True
    # ``REAL_HOME / ".hermes" / "bin"``: el HOME tambien tiene bin/ (uv del instalador).
    if home_hint or any(re.search(r"[Hh][Oo][Mm][Ee]", p) for p in primaries):
        return True
    if nxt in _PROJECT_SUBDIRS or not primaries:
        return nxt not in _PROJECT_SUBDIRS
    # ``work / "demo" / ".hermes"``: un segmento literal entre la raiz y el nombre es una
    # subcarpeta (el HOME de un usuario de prueba), salvo que nombre un proyecto
    # (``tmp_path / "proj" / ".hermes"``).
    lit = re.match(r"^[rbuf]*[\"'](.*)[\"']$", primaries[0])
    if lit:
        return not _PROJECT_LITERAL_RE.match(lit.group(1))
    return not _PROJECT_OPERAND_RE.match(_primary_name(primaries[0]))


def _split_args(args: str) -> list[str]:
    """Argumentos (de nivel superior) ya escritos de una llamada, del ultimo al primero."""
    parts, depth, cur, quote = [], 0, "", ""
    for ch in args:
        if quote:
            quote = "" if ch == quote else quote
        elif ch in "\"'":
            quote = ch
        elif ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
        elif ch == "," and depth == 0:
            parts.append(cur.strip())
            cur = ""
            continue
        cur += ch
    parts.append(cur.strip())
    return [a for a in reversed(parts) if a]


def home_fix(text: str, old: str = ".hermes", new: str = ".clawksis") -> str:
    """Mapea la carpeta HOME ``old`` -> ``new`` solo en contextos de HOME."""
    if old not in text:
        return text
    esc = re.escape(old)
    brand = old.lstrip(".")
    fmt = {"old": esc, "brand": re.escape(brand)}
    env_home = re.compile(rf"\b{re.escape(brand.upper())}_HOME\b")
    project_use = "|".join(re.escape(d) for d in sorted(_PROJECT_SUBDIRS))

    def _hints(pos: int) -> tuple[bool, bool]:
        """(home_hint, project_hint) de la linea en ``pos``: ``HERMES_HOME`` en la linea o
        ``<var con home> = ...``; o ``var = ... / ".hermes"`` con ``var / "environment.json"``
        (u otra componente local de proyecto) mas adelante en el archivo."""
        start = text.rfind("\n", 0, pos) + 1
        end = text.find("\n", pos)
        line = text[start : end if end >= 0 else len(text)]
        m = re.match(
            r"\s*(?:(?:const|let|var)\s+)?(\w+)\s*(?::\s*[\w.|<> ]+)?=[^=>]", line
        )
        var = m.group(1) if m else ""
        if env_home.search(line) or re.search(r"[Hh][Oo][Mm][Ee]", var):
            return True, False
        used = var and re.search(rf"\b{var}\s*/\s*[\"'](?:{project_use})[\"']", text)
        return False, bool(used)

    for pat in _HOME_CTX:
        rx = re.compile(_fmt(pat, fmt) + _HOME_END)
        text = rx.sub(lambda m: m.group(1) + m.group(2) + new + m.group(2), text)

    def _join(m: re.Match[str]) -> str:
        home_hint, project_hint = _hints(m.end())
        nxt = _next_component(text, m.end())
        if not project_hint and _home_operand(
            _primaries_before(text, m.start()), nxt, home_hint
        ):
            return m.group(1) + m.group(2) + new
        return m.group(0)

    text = re.compile(_fmt(_JOIN_RE.pattern, fmt) + _HOME_END).sub(_join, text)

    def _call(m: re.Match[str]) -> str:
        fn, args = m.group("fn"), m.group("args")
        short = fn.rsplit(".", 1)[-1]
        if short not in _CALL_FNS:
            return m.group(0)
        if short in ("join", "joinpath") and "." in fn and not args.strip():
            # X.join(".hermes") / X.joinpath(".hermes"): el operando es el receptor.
            primaries = _primaries_before(
                text, m.start("fn") + len(fn) - len(short) - 1
            )
        else:
            primaries = _split_args(args)
        home_hint, project_hint = _hints(m.end())
        if not project_hint and _home_operand(
            primaries, _next_component(text, m.end()), home_hint
        ):
            return m.group(0)[: m.start("q") - m.start()] + m.group("q") + new
        return m.group(0)

    text = re.compile(_fmt(_CALL_RE.pattern, fmt) + _HOME_END).sub(_call, text)

    # Plugins de proyecto (prosa/docs): ./.hermes/plugins, `.hermes/plugins/<name>/`. No tras
    # otra ruta (``/local/.hermes/plugins`` junto a ``/local/.hermes/desktop-plugins``).
    return re.sub(rf"(?:(?<=\./)|(?<![\w/-])){esc}(?=/{_PLUGINS_DIR}\b)", new, text)


def _fmt(pat: str, fmt: dict[str, str]) -> str:
    for k, v in fmt.items():
        pat = pat.replace("{" + k + "}", v)
    return pat


# Archivos de upstream donde ``.hermes`` es SIEMPRE la carpeta HOME del usuario
# (nunca la config local de un proyecto), aunque no aparezca en un contexto que
# ``home_fix`` reconozca: ``.hermes`` -> ``.clawksis`` en todo el archivo (respetando el
# fin de nombre: ``.hermes-update-in-progress`` no es la carpeta).
HOME_DIR_FILES = {
    # HX001 (code health): detecta el HOME hardcodeado comparando la componente
    # de ruta con ``.hermes``; en el fork el HOME es ``.clawksis``.
    "scripts/code_health/py_rules.py",
    # Helpers del HOME: ``root.name == ".hermes"``, ``user_home() / (".hermes" + suffix)``,
    # ``os.path.basename(home) == ".hermes"``, ``".hermes" in parts[:-1]``.
    "hermes_constants.py",
    "hermes_state_holders.py",
    "agent/redact.py",
    "tests/agent/test_redact.py",
    # Espejos del HOME dentro del sandbox (``.../<task>/home/.hermes``, ``/root/.hermes``) y
    # credenciales del HOME del sandbox (``PurePosixPath(".hermes", ...)``).
    "agent/file_safety.py",
    "gateway/media_fetch.py",
    "tools/environments/modal.py",
    "tools/environments/ssh.py",
    # Backups: un zip trae ``.hermes/config.yaml`` (el HOME empaquetado).
    "hermes_cli/backup_restore.py",
    # Modulos de Nix y su doc: ``${cfg.stateDir}/.hermes``, ``${userHome}/.hermes``.
    "nix/nixosModules.nix",
    "nix/homeManagerModules.nix",
    "nix/checks.nix",
    "website/docs/getting-started/nix-setup.md",
    # Instalador nativo (``format!(".hermes{suffix}")``) y el HOME remoto del desktop por
    # SSH (``/\.hermes\/desktop-ssh\//``, ``"\/home\/alice\/\.hermes"``).
    "apps/bootstrap-installer/src-tauri/src/paths.rs",
    "apps/desktop/electron/remote-lifecycle.test.ts",
}

# Nombres de header HTTP: el blanket rebrandea ``X-Hermes-Foo`` -> ``X-Clawksis-Foo``
# pero ``x-hermes-foo`` -> ``x-clawk-foo``, que es OTRO header (los nombres no
# distinguen mayusculas). Ej.: el sidecar de Photon leia ``x-clawk-sidecar-token``
# mientras el adapter enviaba ``X-Clawksis-Sidecar-Token`` (401 en cada request).
# Se alinea la forma en minusculas (y los MIME ``application/x-hermes-*``, de paso
# coherentes entre si) con ``x-clawksis-``.
_HEADER_RE = re.compile(r"(?<![\w-])([Xx]-)hermes-")

# Wake words por defecto de los adapters iMessage (photon, bluebubbles):
# ``(?<![\w@])@?hermes\b`` es el nombre del producto, que en el fork tiene dos
# formas ("Clawksis" y el comando "clawk"); el blanket dejaba solo ``clawk``.
_WAKE_WORD_RE = re.compile(r"(?<=@\?)hermes(?=\\[sb])")

# URLs de repos de TERCEROS en GitHub (catalogo de plugins, docs, tests): el nombre del
# repo es de su autor (``oxylabs/hermes-web-oxylabs``, ``NousResearch/hermes-official-plugins``);
# rebrandearlo deja links e installs apuntando a repos que no existen. Solo el repo propio
# de upstream (``NousResearch/hermes-agent``) se remapea al fork via CONTENT_MAP.
# El repo propio se reconoce sin distinguir mayusculas (``nousresearch/hermes-agent``,
# ``NousResearch/Hermes-Agent``: GitHub no las distingue). Los owners de ejemplo
# (``example/``, ``you/``, ``e2e-fork/``, ``$REPO_ID/``) no son terceros: se rebrandean como
# el resto del archivo (el fixture de ``test_release_entrypoint`` usa ``example/hermes-agent``
# en el remote Y en las URLs esperadas). ``(?<![\w.-])`` evita que ``api.github.com/repos/..``
# se lea como ``github.com/repos/...`` (un "tercero" llamado ``repos``).
_THIRD_PARTY_URL_RE = re.compile(
    r"(?<![\w.-])(?:https?://)?(?:www\.)?"
    r"(?:github\.com|raw\.githubusercontent\.com|codeload\.github\.com|api\.github\.com/repos)"
    r"/(?!(?i:nousresearch/hermes-agent)(?:\.git)?(?![\w.-]))"
    r"(?!(?:example|you|e2e-fork|\$\w+|\$\{\w+\})/)"
    r"[^\s\"'`)\]>]*[Hh][Ee][Rr][Mm][Ee][Ss][^\s\"'`)\]>]*"
)

# Repo propio en cualquier capitalizacion -> repo del fork (CONTENT_MAP solo cubre la forma
# exacta ``NousResearch/hermes-agent``): en URLs de GitHub (``github.com/nousresearch/
# hermes-agent``, ``git@github.com:...``, regex ``github\.com/``) y como slug con subruta o
# ``.git`` (``skills-sh/nousresearch/hermes-agent/<skill>``, ``nousresearch/hermes-agent/
# skills/``, ``)nousresearch/hermes-agent(\.git)?`` en install.sh). La imagen de Docker
# ``nousresearch/hermes-agent[:tag]`` no lleva subruta y sigue el blanket.
_OWN_REPO_URL_RE = re.compile(
    r"(?i)(github(?:\\)?\.com[/:])nousresearch/hermes-agent(?![\w-])"
)
_OWN_REPO_SLUG_RE = re.compile(
    r"(?i)(?<![\w.-])(?<!/r/)(?<!\.io/)nousresearch/hermes-agent(?=/|\.git\b|\(\\\.git\))"
)
_OWN_REPO = "samuelgradientai-sys/clawksis-agent"

# Variantes en Mixed_Case de una variable de entorno (``Hermes_Yolo_Mode`` para
# ``HERMES_YOLO_MODE`` en los tests de entorno que no distinguen mayusculas): siguen al
# nombre rebrandeado (``Clawk_Yolo_Mode``), no al blanket ``Hermes`` -> ``Clawksis``. Solo
# si el archivo nombra la variable en mayusculas: ``Hermes_Gateway`` (la Scheduled Task de
# Windows) no es una variable y queda ``Clawksis_Gateway``.
_ENV_CASE_RE = re.compile(r"\bHermes_([A-Z][A-Za-z0-9]*(?:_[A-Za-z0-9]+)*)\b")

# Nombre de la DISTRIBUCION (dist-info, egg-info, ``__editable__``, metadata ``Name``):
# el fork se instala como ``clawksis-agent`` -> ``clawksis_agent``; el blanket dejaba
# ``clawk_agent``. Los grupos de entry points (``hermes_agent.plugins``,
# ``.memory_providers``, ``.plugin_capabilities``) son API de plugins y siguen ``clawk_agent``.
_DIST_NAME_RE = re.compile(
    r"(?<![A-Za-z0-9])hermes_agent(?=[-_]\d|\.(?:egg|dist)-info|[\"'])"
)

# Alternancias de nombres con prefijo (``^hermes-(serve|dashboard)...$`` en un regex):
# si los nombres completos no comparten prefijo rebrandeado (``clawk-serve`` pero
# ``clawksis-dashboard``) se expanden a ``(?:clawk-serve|clawksis-dashboard)``.
_PREFIX_ALT_RE = re.compile(
    r"\bhermes-\((?:\?:)?([a-z][a-z0-9_]*(?:\|[a-z][a-z0-9_]*)+)\)"
)

# ``x.startswith("HERMES_HOME=")`` con un corte fijo ``x[12:]`` en la misma linea o la
# siguiente: el literal rebrandeado cambia de largo (``CLAWK_HOME=`` tiene 11), asi que el
# corte se ajusta al largo nuevo.
_STARTSWITH_RE = re.compile(
    r"\.startswith\(\s*[bru]*([\"'])((?:(?!\1)[^\n])*?(?:hermes|Hermes|HERMES)(?:(?!\1)[^\n])*?)\1\s*\)"
)

_ASSETS_HOST_RE = re.compile(r"\bhermes-assets\.nousresearch\.com\b")

# Datos que DEBEN quedar verbatim en un archivo puntual (el rebrand los
# corromperia): se stashean igual que los IDs de modelo. Clave = path de upstream.
VERBATIM = {
    # Vectores SigV4 fijados contra botocore: la firma cubre el path
    # (/hermes-releases/HermesBundled-...), rebrandear el path invalida la firma.
    "tests/scripts/test_release_r2.py": re.compile(
        r"(?s)@pytest\.mark\.parametrize\('method,path,query,payload,scope,signature'"
        r".*?\ndef test_independent_sigv4_vectors\b.*?Signature=\{signature\}'\)"
    ),
    # remote_github_repo con pushInsteadOf 'https://github.com/NousResearch/' -> fork/:
    # la URL y el resultado esperado deben seguir nombrando el org reescrito.
    "tests/scripts/test_release_tags.py": re.compile(
        r"\b(?:NousResearch|fork)/hermes-agent\b"
    ),
    # Host real del mirror de binarios de PM (``pm/artifact-mirror.json``), que ``pm.network``
    # reconoce para diagnosticar bloqueos de Cloudflare. Los RELEASES de Hermes del mismo
    # host (``source_releases.py``) si se rebrandean: el fork no debe descargarlos.
    "pm/network.py": _ASSETS_HOST_RE,
    "pm/artifact-mirror.json": _ASSETS_HOST_RE,
    "tests/hermes_cli/test_release_channels.py": _ASSETS_HOST_RE,
}


# Solo estos tipos de archivo se rebrandean en contenido (igual que rebrand.sh).
REBRAND_EXTS = {
    ".py",
    ".toml",
    ".json",
    ".md",
    ".sh",
    ".ps1",
    ".yml",
    ".yaml",
    ".html",
    ".tsx",
    ".ts",
    ".js",
    ".txt",
    ".cfg",
    ".ini",
    ".rst",
    # Agregados en el sync a v0.22.5: sin estos, upstream traia "hermes" en
    # scripts de build (.mjs/.cjs), nix, Rust, CSS (clases que el TSX ya
    # nombra "clawk-*"), shells fish, plantillas y manifests.
    ".mjs",
    ".cjs",
    ".mts",
    ".cts",
    ".jsx",
    ".nix",
    ".rs",
    ".fish",
    ".css",
    ".scss",
    ".example",
    ".ahk",
    ".xml",
    ".plist",
    ".bat",
    ".cmd",
    ".desktop",
    ".service",
    ".tmpl",
    ".h",
    ".c",
    ".dockerfile",
    ".mdx",
}
REBRAND_BASENAMES = {"Dockerfile", "dockerfile", "activate", "justfile", "uv.lock"}


def _rebrandable(name: str, content: bytes) -> bool:
    ext = ("." + name.rsplit(".", 1)[-1]).lower() if "." in name else ""
    if ext in REBRAND_EXTS or name in REBRAND_BASENAMES:
        return True
    # Scripts sin extension (bin/*, s6 run, wrappers): solo si tienen shebang.
    return not ext and content.startswith(b"#!")


def git(*args: str, check: bool = True) -> str:
    res = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if check and res.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} fallo:\n{res.stderr.strip()}")
    return res.stdout


def git_bytes(*args: str) -> bytes | None:
    res = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        check=False,
    )
    return res.stdout if res.returncode == 0 else None


def show(rev: str, path: str) -> bytes | None:
    return git_bytes("show", f"{rev}:{path}")


def map_path(p: str) -> str:
    for old, new in PATH_MAP:
        p = p.replace(old, new)
    return p


def _map_text(text: str) -> str:
    for old, new in CONTENT_MAP:
        text = text.replace(old, new)
    return text


def _env_case(m: re.Match[str], text: str) -> str:
    env = "HERMES_" + m.group(1).upper()
    if re.search(rf"(?<![A-Za-z0-9_]){env}(?![A-Za-z0-9_])", text):
        return "Clawk_" + m.group(1)
    return m.group(0)


def _prefix_alt(m: re.Match[str]) -> str:
    names = [_map_text("hermes-" + alt) for alt in m.group(1).split("|")]
    if all(n.startswith("clawk-") for n in names):
        return m.group(0)
    return "(?:" + "|".join(names) + ")"


def _fix_prefix_slices(text: str) -> str:
    if "startswith" not in text:
        return text
    lines = text.split("\n")
    for i, line in enumerate(lines):
        for m in _STARTSWITH_RE.finditer(line):
            n_old, n_new = len(m.group(2)), len(_map_text(m.group(2)))
            if n_old == n_new:
                continue
            for j in (i, i + 1)[: len(lines) - i]:
                lines[j] = re.sub(rf"\[\s*{n_old}\s*:\s*\]", f"[{n_new}:]", lines[j])
    return "\n".join(lines)


def rebrand(content: bytes, path: str) -> bytes:
    name = path.rsplit("/", 1)[-1]
    if path.startswith("contributors/") or not _rebrandable(name, content):
        return content
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        return content
    # Stash IDs de modelo Hermes detras de placeholders inertes (NUL-delimitados,
    # imposibles en fuente) para que el blanket hermes->clawk no los corrompa.
    stash: dict[str, str] = {}

    def _stash(m: re.Match[str]) -> str:
        key = f"\x00MODELID{len(stash)}\x00"
        stash[key] = m.group(0)
        return key

    if path in VERBATIM:
        text = VERBATIM[path].sub(_stash, text)
    text = _MODEL_ID_RE.sub(_stash, text)
    text = _THIRD_PARTY_URL_RE.sub(_stash, text)
    text = _OWN_REPO_URL_RE.sub(lambda m: m.group(1) + _OWN_REPO, text)
    text = _OWN_REPO_SLUG_RE.sub(_OWN_REPO, text)
    text = home_fix(text)
    if path in HOME_DIR_FILES:
        text = re.sub(r"\.hermes" + _HOME_END, ".clawksis", text)
    text = _HEADER_RE.sub(r"\1clawksis-", text)
    text = _WAKE_WORD_RE.sub("clawk(?:sis)?", text)
    text = _ENV_CASE_RE.sub(lambda m: _env_case(m, text), text)
    text = _DIST_NAME_RE.sub("clawksis_agent", text)
    text = _PREFIX_ALT_RE.sub(_prefix_alt, text)
    text = _fix_prefix_slices(text)
    text = _map_text(text)
    for key, orig in stash.items():
        text = text.replace(key, orig)
    return text.encode("utf-8")


_WS = re.compile(rb"\s+")


def norm(content: bytes | None) -> bytes:
    """Forma canonica para comparar igualdad: SIN ningun whitespace.

    El squash inicial del fork dejo CRLF, espaciado doble y un reformateo
    estilo black (wrapping/alineacion/trailing commas distintos); todo eso es
    ruido sin semantica para detectar si el fork cambio de verdad un archivo.
    Solo se usa para clasificar — el contenido que se escribe nunca pasa por
    aca."""
    if content is None:
        return b""
    out = _WS.sub(b"", content)
    for a, b in ((b",)", b")"), (b",]", b"]"), (b",}", b"}")):
        out = out.replace(a, b)
    return out


def match_eol(new: bytes, like: bytes | None) -> bytes:
    """Preserva el line ending que ya usa el archivo del fork (evita diffs
    fantasma por CRLF)."""
    if like and b"\r\n" in like and b"\r\n" not in new:
        return new.replace(b"\n", b"\r\n")
    return new


def ensure_upstream() -> None:
    res = subprocess.run(
        ["git", "remote", "get-url", "upstream"],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    if res.returncode != 0:
        git("remote", "add", "upstream", UPSTREAM_URL)
        print(f"[sync] remote upstream agregado: {UPSTREAM_URL}")


def rev_exists(rev: str) -> bool:
    res = subprocess.run(
        ["git", "cat-file", "-e", f"{rev}^{{commit}}"],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    return res.returncode == 0


def fetch_rev(rev: str) -> None:
    if rev_exists(rev):
        return
    print(f"[sync] trayendo {rev} de upstream...")
    for refspec in (
        ["fetch", "--depth", "1", "upstream", "tag", rev],
        ["fetch", "upstream", rev],
    ):
        res = subprocess.run(
            ["git", *refspec],
            cwd=ROOT,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            check=False,
        )
        if res.returncode == 0 and rev_exists(rev):
            return
    raise RuntimeError(f"No pude traer '{rev}' de upstream.")


def ensure_history(state: dict) -> None:
    last = state["last_synced_commit"]
    if rev_exists(last):
        return
    since = state.get("last_synced_date", "").split("T")[0]
    print(f"[sync] historial local no tiene {last[:9]}; fetch de upstream main...")
    args = ["fetch", "upstream", "main"]
    if since:
        args.insert(1, f"--shallow-since={since}")
    subprocess.run(
        ["git", *args],
        cwd=ROOT,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        check=False,
    )
    if not rev_exists(last):
        raise RuntimeError(
            f"El commit base {last[:9]} sigue sin estar disponible. "
            f"Corre: git fetch upstream main"
        )


def latest_release_tag() -> str:
    res = subprocess.run(
        [
            "gh",
            "api",
            "repos/NousResearch/hermes-agent/releases/latest",
            "--jq",
            ".tag_name",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if res.returncode == 0 and res.stdout.strip():
        return res.stdout.strip()
    # Fallback sin gh: tags por ls-remote, orden calver
    out = git("ls-remote", "--tags", "upstream")
    tags = re.findall(r"refs/tags/(v[\d.]+)$", out, flags=re.MULTILINE)
    if not tags:
        raise RuntimeError("No encontre tags en upstream (¿gh y red ok?).")
    return max(tags, key=lambda t: [int(x) for x in re.findall(r"\d+", t)])


def parse_changes(last: str, target: str) -> list[tuple[str, str]]:
    """Devuelve [(status, upstream_path)]; renames se descomponen en D + A."""
    raw = git("diff", "--name-status", "-z", "-M", last, target)
    toks = raw.split("\0")
    changes: list[tuple[str, str]] = []
    i = 0
    while i < len(toks):
        status = toks[i].strip()
        if not status:
            i += 1
            continue
        if status[0] in ("R", "C"):
            old, new = toks[i + 1], toks[i + 2]
            if status[0] == "R":
                changes.append(("D", old))
            changes.append(("A", new))
            i += 3
        else:
            changes.append((status[0], toks[i + 1]))
            i += 2
    return changes


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):  # consolas Windows cp1252
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument(
        "--target", help="tag o commit de upstream (default: ultimo release)"
    )
    ap.add_argument(
        "--apply", action="store_true", help="escribir cambios (default: dry-run)"
    )
    args = ap.parse_args()

    state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    skip_patterns = state.get("skip_paths", [])
    ensure_upstream()
    ensure_history(state)

    target = args.target or latest_release_tag()
    fetch_rev(target)
    target_sha = git("rev-parse", "--verify", f"{target}^{{commit}}").strip()
    last = state["last_synced_commit"]
    if target_sha == last:
        print(f"[sync] ya estas sincronizado con {target} ({last[:9]}).")
        return 0

    print(f"[sync] upstream {last[:9]} -> {target} ({target_sha[:9]})")
    changes = parse_changes(last, target_sha)
    print(f"[sync] {len(changes)} cambios de archivo en upstream\n")

    replaced, added, deleted, already, skipped, diverged = [], [], [], [], [], []
    # Modo ejecutable de upstream (100755): write_bytes no lo conserva, y sin
    # +x se rompen el lanzador `clawk`, los run de s6 en Docker, scripts...
    exec_paths = {
        ln.split("\t", 1)[1]
        for ln in git("ls-tree", "-r", target_sha).splitlines()
        if ln.startswith("100755 ")
    }

    written_py: list[str] = []

    def write_target(dest: Path, data: bytes, up_path: str) -> None:
        dest.write_bytes(data)
        if up_path in exec_paths:
            dest.chmod(dest.stat().st_mode | 0o111)
        if dest.suffix == ".py":
            written_py.append(str(dest))

    for status, up_path in changes:
        if any(fnmatch.fnmatch(up_path, pat) for pat in skip_patterns):
            skipped.append(up_path)
            continue
        fork_path = map_path(up_path)
        dest = ROOT / fork_path
        ours = dest.read_bytes() if dest.is_file() else None
        base = show(last, up_path)
        targ = show(target_sha, up_path)
        base_r = rebrand(base, up_path) if base is not None else None
        targ_r = rebrand(targ, up_path) if targ is not None else None

        if targ_r is None:  # upstream lo borro
            if ours is None:
                already.append(fork_path)
            elif norm(ours) == norm(base_r):
                deleted.append(fork_path)
                if args.apply:
                    dest.unlink()
            else:
                diverged.append(
                    (
                        fork_path,
                        up_path,
                        "upstream lo borra, fork lo modifico",
                    )
                )
        elif ours is None:
            if base_r is None or status == "A":
                added.append(fork_path)
                if args.apply:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    write_target(dest, targ_r, up_path)
            else:
                diverged.append(
                    (
                        fork_path,
                        up_path,
                        "upstream lo modifica, fork lo elimino",
                    )
                )
        elif norm(ours) == norm(targ_r):
            already.append(fork_path)
        elif norm(ours) == norm(base_r):
            replaced.append(fork_path)
            if args.apply:
                write_target(dest, match_eol(targ_r, ours), up_path)
        else:
            diverged.append((fork_path, up_path, "cambios propios del fork"))

    def listing(title: str, items: list[str]) -> None:
        if items:
            print(f"  {title} ({len(items)}):")
            for it in items:
                print(f"    {it}")
            print()

    mode = "APLICADO" if args.apply else "DRY-RUN (nada escrito; usa --apply)"
    print(f"=== Resultado [{mode}] ===\n")
    listing("Actualizados desde upstream", replaced)
    listing("Nuevos", added)
    listing("Borrados", deleted)
    listing("Saltados por skip_paths", skipped)
    if already:
        print(f"  Sin cambios reales (ya al dia / solo espaciado): {len(already)}\n")
    if diverged:
        print(f"  DIVERGENTES — requieren merge manual ({len(diverged)}):")
        for fork_path, up_path, why in diverged:
            print(f"    {fork_path}  [{why}]")
        print()

    if args.apply and diverged:
        import difflib

        PENDING_DIR.mkdir(parents=True, exist_ok=True)
        report = [
            "# Merges pendientes de upstream\n",
            f"Sync {last[:9]} -> {target} ({target_sha[:9]})\n",
        ]
        for fork_path, up_path, why in diverged:
            safe = fork_path.replace("/", "__")
            base = show(last, up_path)
            targ = show(target_sha, up_path)
            base_r = rebrand(base, up_path) if base is not None else b""
            targ_r = rebrand(targ, up_path) if targ is not None else b""
            (PENDING_DIR / f"{safe}.theirs").write_bytes(targ_r)
            diff = difflib.unified_diff(
                base_r.decode("utf-8", "replace").splitlines(keepends=True),
                targ_r.decode("utf-8", "replace").splitlines(keepends=True),
                fromfile=f"a/{fork_path}",
                tofile=f"b/{fork_path}",
            )
            (PENDING_DIR / f"{safe}.patch").write_text("".join(diff), encoding="utf-8")
            report.append(f"- `{fork_path}` — {why}\n")
        (PENDING_DIR / "REPORT.md").write_text("".join(report), encoding="utf-8")
        print(
            f"  Material para los merges manuales en {PENDING_DIR.relative_to(ROOT)}/"
        )
        print(
            "  (aplicar cada .patch a mano sobre el archivo del fork y borrar pending/)\n"
        )

    if args.apply and written_py:
        # El CI del fork exige `ruff format --check .` (upstream no formatea su
        # arbol): formatear lo que trae el sync para que no rompa el lint.
        for i in range(0, len(written_py), 500):
            subprocess.run(
                ["ruff", "format", "--quiet", *written_py[i : i + 500]],
                cwd=ROOT,
                check=False,
            )

    if args.apply:
        state["last_synced_commit"] = target_sha
        if re.fullmatch(r"v[\d.]+", target):
            state["last_synced_tag"] = target
        state["last_synced_date"] = git("log", "-1", "--format=%cI", target_sha).strip()
        STATE_FILE.write_text(
            json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print("[sync] sync_state.json actualizado. Proximos pasos:")
        print("  1. Resolver pending/ si hay divergentes")
        print("  2. Revisar:  git status && git diff --stat")
        print("  3. Smoke test del CLI y commitear")

    return 0


if __name__ == "__main__":
    sys.exit(main())
