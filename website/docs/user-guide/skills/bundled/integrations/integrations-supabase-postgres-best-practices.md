---
title: "Supabase Postgres Best Practices — Optimize Postgres queries, indexes and schemas (Supabase)"
sidebar_label: "Supabase Postgres Best Practices"
description: "Optimize Postgres queries, indexes and schemas (Supabase)"
---

{/* This page is auto-generated from the skill's SKILL.md by website/scripts/generate-skill-docs.py. Edit the source SKILL.md, not this page. */}

# Supabase Postgres Best Practices

Optimize Postgres queries, indexes and schemas (Supabase).

## Skill metadata

| | |
|---|---|
| Source | Bundled (installed by default) |
| Path | `skills/integrations/supabase-postgres-best-practices` |
| Version | `1.1.1` |
| Author | Supabase |
| License | MIT |
| Platforms | linux, macos, windows |
| Tags | `postgres`, `supabase`, `performance`, `indexes`, `sql`, `rls`, `schema` |

## Reference: full SKILL.md

:::info
The following is the complete skill definition that Clawksis loads when this skill is triggered. This is what the agent sees as instructions when the skill is active.
:::

# Supabase Postgres Best Practices

Comprehensive performance optimization guide for Postgres, maintained by Supabase. Contains rules across 8 categories, prioritized by impact to guide automated query optimization and schema design.

## When to Apply

Reference these guidelines when:
- Writing SQL queries or designing schemas
- Implementing indexes or query optimization
- Reviewing database performance issues
- Configuring connection pooling or scaling
- Optimizing for Postgres-specific features
- Working with Row-Level Security (RLS)

Spanish requests too: postgres, optimización de consultas/queries, índices/indexes, índice
faltante, RLS/seguridad a nivel de fila, rendimiento/performance, consultas lentas,
EXPLAIN/plan de consulta, pooling/conexiones, particionado, esquema/schema,
migraciones/constraints, llave primaria/foreign key, deadlock/bloqueos, SKIP LOCKED/colas,
paginación, N+1, upsert, vacuum, pg_stat_statements, full text search, JSONB.

## Rule Categories by Priority

| Priority | Category | Impact | Prefix |
|----------|----------|--------|--------|
| 1 | Query Performance | CRITICAL | `query-` |
| 2 | Connection Management | CRITICAL | `conn-` |
| 3 | Security & RLS | CRITICAL | `security-` |
| 4 | Schema Design | HIGH | `schema-` |
| 5 | Concurrency & Locking | MEDIUM-HIGH | `lock-` |
| 6 | Data Access Patterns | MEDIUM | `data-` |
| 7 | Monitoring & Diagnostics | LOW-MEDIUM | `monitor-` |
| 8 | Advanced Features | LOW | `advanced-` |

## How to Use

Read individual rule files for detailed explanations and SQL examples:

```
references/query-missing-indexes.md
references/query-partial-indexes.md
references/_sections.md
```

Each rule file contains:
- Brief explanation of why it matters
- Incorrect SQL example with explanation
- Correct SQL example with explanation
- Optional EXPLAIN output or metrics
- Additional context and references
- Supabase-specific notes (when applicable)

## References

- https://www.postgresql.org/docs/current/
- https://supabase.com/docs
- https://wiki.postgresql.org/wiki/Performance_Optimization
- https://supabase.com/docs/guides/database/overview
- https://supabase.com/docs/guides/auth/row-level-security
