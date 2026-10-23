---
title: "Excel Template Generator — Create Excel .xlsx business templates and workbooks"
sidebar_label: "Excel Template Generator"
description: "Create Excel .xlsx business templates and workbooks"
---

{/* This page is auto-generated from the skill's SKILL.md by website/scripts/generate-skill-docs.py. Edit the source SKILL.md, not this page. */}

# Excel Template Generator

Create Excel .xlsx business templates and workbooks.

## Skill metadata

| | |
|---|---|
| Source | Bundled (installed by default) |
| Path | `skills/productivity/excel-template-generator` |
| Version | `1.0.0` |
| Author | Clawksis Gradient AI |
| License | MIT |
| Platforms | linux, macos, windows |
| Tags | `excel`, `xlsx`, `templates`, `spreadsheet`, `inventory`, `sales`, `openpyxl` |

## Reference: full SKILL.md

:::info
The following is the complete skill definition that Clawksis loads when this skill is triggered. This is what the agent sees as instructions when the skill is active.
:::

# excel-template-generator — crear plantillas Excel profesionales

Esta skill crea archivos .xlsx seguros y editables para operaciones de negocio.

Usala cuando el usuario pida crear plantillas Excel, generar archivos .xlsx, crear formatos de inventario, ventas, clientes, costos, postventa o preparar hojas de seguimiento operativo.

Frases típicas (ES + EN): 'crear Excel', 'plantilla Excel', 'generar xlsx', 'crear plantilla
de inventario', 'plantilla de ventas', 'plantilla postventa', 'spreadsheet template', 'Excel
template', 'inventory workbook', 'sales workbook'. También dashboards y hojas de costos o
clientes.

## Seguridad

- No usa macros.
- No ejecuta fórmulas externas.
- No incluye tokens, API keys ni secretos.
- No sobrescribe archivos existentes salvo confirmación explícita.
- Guarda archivos en rutas explícitas o en ~/clawksis_exports/excel_templates/.
- Si se modifica un archivo existente, primero debe hacerse backup.

## Dependencia

Requiere openpyxl instalado en el entorno de Clawksis:

/opt/clawksis-agent/.venv/bin/python -m pip install "openpyxl==3.1.5"

## Plantillas disponibles

- inventory: inventario con SKU, producto, categoría, stock, costo, precio, margen, valor inventario y alerta de stock bajo.
- sales: ventas diarias con cliente, producto, cantidad, precio, descuento, total, método de pago, canal y estado.
- postventa: seguimiento postventa con cliente, caso, estado, prioridad, responsable, costo adicional y próxima acción.

## Enlace descargable en dashboard

Cuando el script imprima una línea como:

download_url=/artifacts/download?path=...

incluye en la respuesta final un link Markdown así:

[Descargar archivo](/artifacts/download?path=...)

No digas que no tienes herramienta send_file si el usuario está usando el dashboard web de Clawksis. En dashboard, usa el link de descarga local generado por el backend.


## Uso

El script vive en:

scripts/generate_template.py

Ejemplo:

/opt/clawksis-agent/.venv/bin/python "$SKILL_DIR/scripts/generate_template.py" --template inventory --business-name "Clawksis" --output "$HOME/clawksis_exports/excel_templates/inventario.xlsx"
