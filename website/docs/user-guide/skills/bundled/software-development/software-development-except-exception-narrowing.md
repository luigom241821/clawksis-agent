---
title: "Except Exception Narrowing — Narrow broad except Exception clauses to specific types"
sidebar_label: "Except Exception Narrowing"
description: "Narrow broad except Exception clauses to specific types"
---

{/* This page is auto-generated from the skill's SKILL.md by website/scripts/generate-skill-docs.py. Edit the source SKILL.md, not this page. */}

# Except Exception Narrowing

Narrow broad except Exception clauses to specific types.

## Skill metadata

| | |
|---|---|
| Source | Bundled (installed by default) |
| Path | `skills/software-development/except-exception-narrowing` |
| Version | `1.0` |
| Author | Clawksis |
| License | MIT |
| Platforms | linux, macos, windows |
| Tags | `python`, `exceptions`, `error-handling`, `logging`, `refactoring`, `code-quality` |

## Reference: full SKILL.md

:::info
The following is the complete skill definition that Clawksis loads when this skill is triggered. This is what the agent sees as instructions when the skill is active.
:::

# Except Exception Narrowing — patrón de mejora

Cuando audites código Python buscando `except Exception:` o `except:` sin especificar el tipo:

## Señales a buscar

- `except Exception: pass` — traga todo sin log
- `except Exception:` (sin especificar) — esconde errores reales
- `except:` — aún peor; captura incluso `SystemExit`/`KeyboardInterrupt`

## Cómo arreglarlo

### 1. Identifica qué puede fallar realmente

| Contexto | Excepción(es) correctas |
|---|---|
| `importlib.util.find_spec()` / `import` | `ImportError` |
| `Path.read_text()` / `open()` | `OSError`, `UnicodeDecodeError` |
| `os.unlink()` / file ops | `OSError` (FileNotFoundError, PermissionError) |
| `json.loads()` | `json.JSONDecodeError`, `TypeError` |
| `config.load_config()` / `getattr()` | `(ImportError, OSError, TypeError)` |
| `subprocess.run()` | `subprocess.TimeoutExpired` (catch first), `OSError`, `ValueError`, `subprocess.SubprocessError` |
| API calls / network | `requests.RequestException`, `aiohttp.ClientError` |

### 2. Siempre añade logging

```python
# ❌ Antes
except Exception:
    pass

# ✅ Después
except (OSError, UnicodeDecodeError) as exc:
    logger.warning("nombre_modulo: contexto de lo que falló (%s)", exc)
```

- Usa `logger.debug()` para recoverable/expected failures
- Usa `logger.warning()` para condiciones anómalas
- Usa `logger.error()` para bugs inesperados

### 3. Niveles de logging

- **debug**: limpieza de temp files, chequeo de módulo no instalado, fallos esperados en config
- **warning**: fallo al leer output que debería estar ahí, error inesperado en batch
- **error**: bugs, datos corruptos, condiciones que deberían investigarse

### 4. Excepciones que NUNCA capturar con `except:`

- `SystemExit` — el programa quiere salir
- `KeyboardInterrupt` — el usuario quiere cancelar
- `GeneratorExit` — el generador se cierra

Siempre usa `except Exception:` como mínimo (que no captura las anteriores), pero mejor aún: especifica.

## Ejemplo real de mejora

```python
# Antes (scrape_tool.py):
    except Exception:
        pass

# Después:
    except (ImportError, OSError):
        logger.debug("scrape: scrapling module import check failed")
```

## Tests

Siempre corre los tests del archivo que tocaste después de cambiar:

```bash
cd /path/to/clawksis-agent
uv run pytest tests/tools/test_scrapegraph_tool.py -v
```

## Referencia

- [Python docs: Built-in Exceptions](https://docs.python.org/3/library/exceptions.html)
- [BLE001 (blind-except) ruff rule](https://docs.astral.sh/ruff/rules/blind-except/)
