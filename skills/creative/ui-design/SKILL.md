---
name: ui-design
description: "Design UI with DESIGN.md tokens, mockups and templates."
version: 1.0.0
author: Clawksis
license: MIT
platforms: [linux, macos, windows]
metadata:
  clawk:
    tags: [design, ui, mockup, tokens, design-system, css, html, sketch]
    related_skills: [diagrams, p5js, claude-design]
---

# UI Design

Three complementary approaches for UI design, depending on what phase of the design process you're in:

| Phase | Approach | What it produces |
|-------|----------|-----------------|
| **Design System** | DESIGN.md token spec | Formal YAML+Markdown spec file with colors, typography, components, and WCAG validation |
| **Exploration** | Sketch (HTML mockups) | 2-3 interactive HTML variants for head-to-head comparison |
| **Implementation** | Design system templates | Catalog of 54 real-world design systems (Stripe, Linear, Vercel, etc.) as CSS/HTML references |

---

## DESIGN.md Token Spec (`references/design-md-full.md`)

Google's open spec for describing a visual identity to coding agents. One file combines YAML front matter (machine-readable design tokens) with Markdown body (human-readable rationale).

### When to use

- User asks for a DESIGN.md file, design tokens, or a design system spec
- User wants consistent UI/brand across multiple projects
- User wants WCAG accessibility validation on their color palette

### File anatomy

```yaml
---
version: alpha
name: Heritage
description: Architectural minimalism meets journalistic gravitas.
colors:
  primary: "#1A1C1E"
  secondary: "#6C7278"
  tertiary: "#B8422E"
typography:
  h1:
    fontFamily: Public Sans
    fontSize: 3rem
    fontWeight: 700
    lineHeight: 1.1
components:
  button-primary:
    backgroundColor: "{colors.tertiary}"
    textColor: "#FFFFFF"
    rounded: "{rounded.sm}"
    padding: 12px
---
```

### Token types

| Type | Format | Example |
|------|--------|---------|
| Color | `#` + hex (sRGB) | `"#1A1C1E"` |
| Dimension | number + unit | `48px`, `-0.02em` |
| Token reference | `{path.to.token}` | `{colors.primary}` |
| Typography | object | `fontFamily`, `fontSize`, etc. |

### Canonical sections (in order)

1. Overview — 2. Colors — 3. Typography — 4. Layout — 5. Elevation — 6. Shapes — 7. Components — 8. Do's and Don'ts

### CLI

Lint, diff, and export via `npx -y @google/design.md`:
- `npx @google/design.md lint DESIGN.md` — structure + WCAG contrast
- `npx @google/design.md diff DESIGN.md DESIGN-v2.md` — regression check
- `npx @google/design.md export --format tailwind DESIGN.md > tailwind.theme.json`
- `npx @google/design.md export --format dtcg DESIGN.md > tokens.json`

See `references/design-md-full.md` for complete reference (all token types, workflow, pitfalls).

---

## Sketch (HTML Mockups) (`references/sketch-full.md`)

Generate 2-3 interactive HTML mockup variants for design exploration. **Never one variant — the point is comparison.**

### Workflow

```
intake → variants → head-to-head → pick winner (or iterate)
```

### Intake

Ask the user (one question at a time):
1. **Feel** — "What should this feel like? Adjectives, emotions, a vibe."
2. **References** — "What apps/sites capture the feel?"
3. **Core action** — "What's the single most important thing a user does on this screen?"

### Variant Stances

Pick one axis and pull apart:
| Axis | Poles |
|------|-------|
| Density | compact / airy |
| Emphasis | content-first / action-first |
| Aesthetic | editorial / utilitarian / playful |
| Layout | single-column / sidebar / split-pane |

### HTML Requirements

- Self-contained HTML, inline `<style>`, system fonts or one Google Font via `<link>`
- Realistic fake content (real sentences, not Lorem ipsum)
- **Interactive** — at least one state transition (toggle, filter, open/close)
- **Verify visually** — use `browser_navigate` + `browser_vision` to catch layout bugs

### Output Structure

```
sketches/
├── 001-calm-editorial/
│   ├── index.html
│   └── README.md
├── 001-utilitarian-dense/
│   ├── index.html
│   └── README.md
└── 002-playful-split/
    ├── index.html
    └── README.md
```

Each README: design stance, key choices, trade-offs, best for.

See `references/sketch-full.md` for the complete workflow, variant naming conventions, theming, interactivity bar, and frontier mode.

---

## Design System Templates (`templates/`)

54 real-world design systems for reference when generating HTML/CSS. Each template captures a site's complete visual language: color palette, typography, component styles, spacing, shadows.

### How to use

1. Pick a design from the catalog below
2. Load the template: `skill_view("ui-design", "templates/<site>.md")`
3. Use the design tokens when generating HTML

### Quick Catalog

| Category | Templates |
|----------|-----------|
| **AI/ML** | Claude, Cohere, ElevenLabs, Minimax, Mistral, Ollama, OpenCode, Replicate, RunwayML, Together, VoltAgent, xAI |
| **Dev Tools** | Cursor, Expo, Linear, Lovable, Mintlify, PostHog, Raycast, Resend, Sentry, Supabase, Superhuman, Vercel, Warp, Zapier |
| **Infra/Cloud** | ClickHouse, Composio, HashiCorp, MongoDB, Sanity, Stripe |
| **Design/Productivity** | Airtable, Cal, Clay, Figma, Framer, Intercom, Miro, Notion, Pinterest, Webflow |
| **Fintech/Crypto** | Coinbase, Kraken, Revolut, Wise |
| **Enterprise/Consumer** | Airbnb, Apple, BMW, IBM, NVIDIA, SpaceX, Spotify, Uber |

### Font Substitution

| Proprietary Font | CDN Substitute |
|-----------------|---------------|
| Geist | Geist (on Google Fonts) |
| sohne-var (Stripe) | Source Sans 3 |
| Berkeley Mono | JetBrains Mono |
| Circular (Spotify) | DM Sans |
| figmaSans | Inter |

For the full 54-template reference, see `references/popular-web-designs-full.md`.

---

## Common Pitfalls

- **Don't use sketch when the design is already locked** — just build it
- **Don't use DESIGN.md for one-off prototypes** — use sketch instead
- **Don't write two identical mockups** — each variant must take a different design stance
- **DESIGN.md hex colors must be quoted strings** — `"#1A1C1E"` not `#1A1C1E`
- **DESIGN.md section order is enforced** — reorder to match canonical list
- **Font substitutes matter** — use the mapping table above, not arbitrary choices

## References

- `references/design-md-full.md` — Complete DESIGN.md spec reference with all token types, lint/export/workflow details
- `references/sketch-full.md` — Complete sketch workflow with variant intake, generation, head-to-head comparison
- `references/popular-web-designs-full.md` — Full 54-template catalog with font substitution and all template names
