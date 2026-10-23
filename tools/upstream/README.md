# Sync con upstream (NousResearch/hermes-agent)

Clawksis es un fork rebrandeado de Hermes Agent que **no comparte historia de
git** con upstream (la historia se recreó en el squash inicial). Además el
árbol difiere por tres capas de ruido: el rebrand `hermes → clawksis/clawk`,
line endings (el fork tiene CRLF, upstream LF) y espaciado inconsistente
heredado del squash. Conclusión: `git merge` / `cherry-pick` / `git apply` no
sirven contra upstream.

Este tooling sincroniza **archivo por archivo**: rebrandea la versión de
upstream con el mismo mapping del rebrand original y compara contenido
*normalizado* (sin CRLF, sin líneas en blanco, sin espacios finales), que es
inmune a todo ese ruido.

## Flujo

```bash
# 1. Ver qué hay para traer (no escribe nada)
python tools/upstream/sync.py                      # vs último release de upstream
python tools/upstream/sync.py --target v2026.6.5   # vs un tag específico

# 2. Aplicar en un branch
git switch -c sync/upstream-v2026.6.5
python tools/upstream/sync.py --target v2026.6.5 --apply

# 3. Resolver divergentes (si hay), revisar, commitear
git status && git diff --stat
```

## Qué hace con cada archivo que upstream cambió

| Estado en el fork                                  | Acción |
|----------------------------------------------------|--------|
| Igual al baseline upstream (módulo rebrand/espaciado) | Lo reemplaza por la versión nueva rebrandeada |
| Ya igual al target                                 | Nada |
| Con cambios propios del fork                       | Lo lista como **divergente** y deja material en `pending/` |
| No existe y upstream lo agrega                     | Lo crea rebrandeado |

Los reemplazos limpios además normalizan de paso el espaciado doble del
squash en ese archivo (la versión nueva viene con el formato sano de
upstream).

## Divergentes (`pending/`)

Con `--apply`, cada archivo divergente deja en `tools/upstream/pending/`:

- `<archivo>.patch` — el diff de upstream **ya rebrandeado** (base → target)
- `<archivo>.theirs` — la versión target completa rebrandeada
- `REPORT.md` — la lista con el motivo de cada uno

El merge se hace a mano (o con Claude): aplicar la intención del `.patch`
sobre el archivo del fork, respetando los cambios propios. `pending/` está en
`.gitignore` — no se commitea.

## Divergentes en lote (desde el sync a v0.22.5)

Para saltos grandes, en este orden:

```bash
python tools/upstream/automerge.py --apply          # .py cuyo delta del fork es solo formato
python tools/upstream/merge3x.py --list lista.txt --apply                    # merges limpios
python tools/upstream/merge3x.py --list lista.txt --apply --write-conflicts  # + marcadores
python tools/upstream/resolve_side.py --prefer theirs --nous-guard tests/...           # tests
python tools/upstream/resolve_side.py --prefer theirs --respect-fork-deletions \
    --nous-guard website/docs/...                                                       # docs
```

- `merge3x.py`: diff3 que ignora lineas en blanco y, en `.py`, trata
  comentarios/docstrings como "trivia" (se fusionan aparte) y formatea los
  tres lados con `ruff format` antes de comparar. Neutraliza el ruido del
  squash y del `ruff format` masivo del fork; solo quedan conflictos reales,
  con marcadores `<<<<<<< fork` / `||||||| base` / `=======` / `>>>>>>> upstream`.
- `resolve_side.py`: resuelve marcadores eligiendo lado por bloque (seguro
  para tests/docs/locales). Respeta bloques que el fork borro a proposito y
  no reintroduce Nous.
- Los conflictos de codigo de produccion se resuelven a mano (o con agentes,
  ver la guia que se uso en el sync a v0.22.5: fork features + upstream structure).

## Rebrand: casos especiales

- Carpeta HOME: `~/.clawksis`. `sync.home_fix()` mapea `.hermes` a `.clawksis`
  solo en contextos de HOME; la config local de un proyecto (`<repo>/.clawk/skills`,
  `.clawk/bin`, `environment.json`, `plans`, adjuntos del desktop, `.clawk.md`) queda
  como `.clawk`. Contextos reconocidos:
  - uniones de rutas `<operando> / ".hermes"` (y `/ (".hermes" + suffix)`,
    `/ ("x" if c else ".hermes")`, subruta en el literal) y llamadas
    `join(A, ".hermes", ...)`, `Path(A, ".hermes")`, `X.joinpath(".hermes")`,
    `PurePosixPath(".hermes", ...)`: es HOME salvo que el operando nombre un proyecto
    (`repo`, `root`, `project*`, `install*`, `cwd`, `work`, ... o el literal `"proj"`) o la
    componente siguiente sea local de proyecto (`bin`, `environment.json`, `plans`,
    adjuntos). Un operando con `home` (`REAL_HOME / ".hermes" / "bin"`) siempre es HOME;
    `tmp_path`, `profile_env`, `pw_dir)`, `Path(os.environ["HOME"])`, cadenas como
    `tmp_path / "alice" / ".hermes"` tambien.
  - shell/prosa: `$HOME/.hermes`, `${HERMES_HOME:-$HOME/.hermes}`, `$HOME/.hermes${suffix}`,
    `${USERPROFILE}/.hermes`, `%h/.hermes` (systemd), `/root`, `/home/<user>`, `/Users/x`,
    `/var/lib/hermes`, `/opt/data`, `/data`, `/your`; miembros de tar sin barra
    (`"root/.hermes/x"`, `home/<user>/.hermes`); `<scratch>/`, `stateDir/`, `tmp_path/`,
    `Path.home()/`, `remote .hermes`; `<root>/.hermes` salvo `<root>/.hermes/{bin,skills}`.
  - f-strings/templates con un home en el placeholder (`f"{self._remote_home}/.hermes"`,
    `` `${fakeHome}/.hermes` ``, `${config.home.homeDirectory}/.hermes`), regex con el punto
    escapado (`\$HOME/\.hermes/`, `~\/\.hermes/`), un literal `".hermes"` en una linea
    que nombra `profiles`, y prosa relativa con subcarpetas que solo tiene el HOME
    (`@file:.hermes/.env`, `.hermes/auth.json`, `.hermes/sessions`, `mcp-tokens`, ...).
  - `.hermes/plugins` es `.clawksis/plugins` tambien en un proyecto (`./.clawksis/plugins`,
    lo que carga `clawk_cli/plugins.py`).
  - `HOME_DIR_FILES` lista archivos donde todo `.hermes` es el HOME (helpers del HOME,
    espejos del HOME del sandbox, nix, `paths.rs`, `remote-lifecycle.test.ts`, ...),
    respetando el fin de nombre (`.hermes-update-in-progress` no es la carpeta).
  - `home_fix(text, old, new)` es parametrico: con `old=".clawk"` muestra donde el arbol
    del fork quedo incoherente con las reglas (asi se alineo el arbol en el sync a v0.22.5).
- Headers HTTP: `x-hermes-foo` -> `x-clawksis-foo` (como `X-Hermes-Foo` ->
  `X-Clawksis-Foo`; los nombres de header no distinguen mayusculas). El esquema de
  Authorization `HermesRoom` se compara en minusculas: `hermesroom` -> `clawksisroom`.
- Variables de entorno en Mixed_Case (`Hermes_Yolo_Mode` para `HERMES_YOLO_MODE`):
  `Clawk_Yolo_Mode`, solo si el archivo nombra la variable en mayusculas
  (`Hermes_Gateway`, la Scheduled Task de Windows, sigue siendo `Clawksis_Gateway`).
- Nombre de la distribucion (`hermes_agent-*.dist-info`, `.egg-info`, `__editable__`,
  metadata `Name`): `clawksis_agent` (el paquete es `clawksis-agent`). Los grupos de entry
  points (`hermes_agent.plugins`, `.memory_providers`, `.plugin_capabilities`) siguen
  `clawk_agent`.
- Toolset de plataforma `hermes-webhook` -> `clawk-webhook` (como todo `clawk-<plataforma>`;
  antes el `hermes-web` historico lo dejaba en `clawksis-webhook`). Las configs viejas con
  `clawksis-webhook` siguen funcionando: `toolset_validation.RENAMED_TOOLSETS`.
- Alternancias con prefijo en regex (`hermes-(serve|dashboard)`): se expanden si los nombres
  no comparten prefijo -> `(?:clawk-serve|clawksis-dashboard)` (la unidad del dashboard es
  `clawksis-dashboard`).
- `x.startswith("HERMES_HOME=")` con un corte fijo `x[12:]` en la misma linea o la siguiente:
  el corte se ajusta al largo del literal rebrandeado (`CLAWK_HOME=` -> `[11:]`).
- Wake words de photon/bluebubbles: `@?hermes\b` -> `@?clawk(?:sis)?\b`.
- URLs: el repo propio en cualquier capitalizacion (`github.com/nousresearch/hermes-agent`,
  `NousResearch/Hermes-Agent`, `skills-sh/nousresearch/hermes-agent/<skill>`,
  `api.github.com/repos/NousResearch/hermes-agent/...`) -> repo del fork. La imagen de
  Docker `nousresearch/hermes-agent[:tag]` sigue el blanket (`nousresearch/clawksis-agent`,
  el nombre que usa `.github/workflows/docker.yml` del fork). Repos de terceros en GitHub
  quedan textuales, salvo owners de ejemplo (`example/`, `you/`, `e2e-fork/`, `$REPO_ID/`).
  La pagina de producto `hermes-agent.nousresearch.com/desktop` -> raiz del repo del fork.
- `VERBATIM` en `sync.py`: datos de un archivo puntual que no se rebrandean
  (vectores SigV4 de `test_release_r2.py`, URLs de `test_release_tags.py`, y el host real
  del mirror de PM `hermes-assets.nousresearch.com` en `pm/network.py`,
  `pm/artifact-mirror.json` y `test_release_channels.py`; los releases de Hermes del mismo
  host en `source_releases.py` si se rebrandean: el fork no debe descargarlos).
- Simbolo de marca: `⚕`/`☤` -> `∇`.
- Modulos-libreria de Nous (`clawk_cli/*nous*.py`, `agent/nous_*.py`,
  `agent/billing_usage.py`, `clawk_cli/cli_billing_mixin.py`): se sincronizan
  porque el codigo de upstream los importa en ~180 sitios; quedan inertes sin
  credenciales Nous. Lo que NO se trae (ver `skip_paths`): el proveedor Nous,
  el login Nous del dashboard, el adaptador del proxy, docs, assets y tests de Nous.

## Ojo al revisar

- **Nous Portal**: upstream puede re-introducir acoplamiento a Nous en la UI
  (menus, pickers, banners). Superficies de producto de Nous van a
  `skip_paths` en `sync_state.json` (acepta globs); los modulos-libreria no
  (ver arriba).
- **Workflows de upstream**: cambios bajo `.github/workflows/` revisarlos con
  cuidado antes de mergear.
- Los PRs del fork van con la cuenta gh `samuelgradientai-sys`.

## Watcher automático

`.github/workflows/upstream-watch.yml` corre diario: si upstream publica un
release más nuevo que `last_synced_tag`, abre un issue en este repo con las
release notes y los comandos de sync. No aplica nada solo.

## Estado

`sync_state.json` registra hasta qué commit/tag de upstream estamos
sincronizados. Lo actualiza `sync.py --apply`; no editarlo a mano salvo para
`skip_paths`.
