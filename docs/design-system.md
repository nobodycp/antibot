# Antibot dashboard — design system

Internal UI for the Django dashboard (extends `dashboard/base.html`). **Source of truth for colors and components:** `dashboard/static/dashboard/css/design-system.css`. **Page chrome & headers:** `dashboard/static/dashboard/css/ui-system.css`. **Motion:** `motion.css`.

---

## 1. Color system

Palette is **derived from sidebar chrome** `#26262a` (`rgb(38 38 42)`), with **B = R + 4** on each step and **±8** per channel between stops:

| Token / role | RGB | Typical use |
|--------------|-----|----------------|
| **D2** `--ds-ref-from-chrome-d2-rgb` | 22 22 26 | App canvas (main scroll), fields, deep pills |
| **D1** `--ds-ref-from-chrome-d1-rgb` | 30 30 34 | Table/card headers, zebra odd, primary buttons |
| **Chrome** `--ds-ref-chrome-rgb` | 38 38 42 | Sidebar, header, footer, zebra even |
| **L1** `--ds-ref-from-chrome-l1-rgb` | 46 46 50 | Cards, table shells, raised surfaces |
| **L2** `--ds-ref-from-chrome-l2-rgb` | 54 54 58 | Row hover, borders (with opacity) |

Semantic mappings (see `:root` in `design-system.css`):

- **Primary text:** `--ds-color-text`
- **Muted:** `--ds-color-text-muted`, **secondary:** `--ds-color-text-secondary`
- **Success / warning / danger:** `--ds-color-success`, `--ds-color-warning`, `--ds-color-danger` (desaturated)
- **Accent (navigation active, focus):** emerald `--ds-ref-accent` / `--ds-ref-accent-strong`

**Do not** introduce one-off hex colors in new templates; add a token in `:root` if a new surface is needed.

---

## 2. Typography

| Role | Token | Notes |
|------|--------|--------|
| Page title | `--ds-text-page-title` / `--ds-text-page-title-lg` | `.ds-page-header__title` |
| Page subtitle | `--ds-text-page-subtitle` / `--ds-text-page-subtitle-sm` | `.ds-page-header__subtitle` |
| Section kicker | `--ds-text-kicker-size` | `.ds-kicker` |
| Card subtitle | `--ds-text-helper` | `.ds-subtitle` |
| Body | `--ds-text-body` (= `--ds-text-sm`) | Main content |
| Labels | `--ds-text-label` (= `--ds-text-xs`) | `.ds-label` |
| Table body | `--ds-text-table-body` | Tables default |
| Buttons | `--ds-text-button` | `.ds-btn` |

**Line heights:** `--ds-leading-tight`, `--ds-leading-snug`, `--ds-leading-body`.

---

## 3. Spacing

Scale: `--ds-space-1` … `--ds-space-8` (0.25rem → 2rem).

Layout tokens:

- `--ds-space-page-header-margin`, `--ds-space-page-header-bottom`
- `--ds-space-section-y` — vertical gap between major blocks (use `.ds-stack-page`)
- `--ds-space-card-inner-y` — card padding rhythm (cards use `ds-card__body` rules)

Main padding is set on `main.dash-main-scroll` in `base.html` (Tailwind). **Inner page vertical rhythm:** `.ds-page-shell` (replaces `min-w-0 w-full space-y-5 text-sm` on tracker/tools shells and home). Larger stacks: `.ds-stack-page` / `.ds-stack-page--tight`.

---

## 4. Components (classes)

| Area | Classes |
|------|---------|
| **App frame** | `#main-content` inside `base.html` |
| **Page column** | `.ds-page-shell` — standard shell wrapper for HTMX-swapped content |
| **Page header** | `.dash-page-header` + `.ds-page-header__*` (see `dashboard_page_header.html`) |
| **Stack sections** | `.ds-stack-page`, `.ds-stack-page--tight` |
| **Cards** | `.ds-card`, `.ds-card__head`, `.ds-card__body`, `.dash-panel` |
| **Stats** | `.dash-stat-tile`, `.ds-stat-tile` |
| **Forms** | `.ds-form-stack`, `.ds-field`, `.ds-label`, `.ds-input`, `.ds-input--compact`, `.ds-select`, `.ds-select--fit`, `.ds-textarea`, `.ds-fieldset` |
| **Icon controls** | `.ds-icon-btn`, `.ds-icon-btn--danger`, `.ds-icon-btn--warning` (toolbar refresh / delete) |
| **Buttons** | `.ds-btn`, modifiers `--primary`, `--inverse`, `--danger`, `--success`, `--sm`, etc. |
| **Tables** | `.table.table`, `.ds-table`, `.tracker-list-table`, `.dash-table-zebra` + zebra/hover in CSS |
| **Toolbar** | `.dash-sticky-toolbar` |
| **Alerts** | `.ds-alert`, `.ds-alert--error`, … |
| **Auth** | `.ds-auth-page`, `.ds-auth-title` |
| **Links** | `.ds-link-muted` |

Tailwind utilities are allowed for **layout** (flex, grid, gap); prefer **DS classes** for color/surfaces on new work.

---

## 5. Tables

- Shell: `.table-container` / `.dash-surface.dash-table-shell` — uses `--ds-color-bg-table-shell`.
- Header row: `--ds-color-bg-table-head`.
- Zebra: `--ds-color-table-row-odd` / `--ds-color-table-row-even`.
- Hover: `--ds-color-table-row-hover`.
- Include partials: `tracker_list_table_open.html` / `close.html` — keep `id`s and HTMX attributes unchanged.

---

## 6. App chrome (no Tailwind zinc in templates)

- **Header:** `dashboard/partials/header.html` — `dash-header-bar`, `dash-header-toggle`, `dash-header-breadcrumb`, `dash-header-chip`, `dash-header-user-rail`, `dash-header-logout`, `dash-header-avatar-*` (see `ui-system.css`).
- **Sidebar:** `dashboard/partials/sidebar.html` — `dash-sidebar-aside`, `dash-sidebar-brand`, `dash-nav-top`, `dash-nav-sub`, `dash-nav-section-btn`, `dash-nav-nested`, `dash-nav-ico`; active route = class `is-active` (set in templates + `base.html` `syncSidebarActive`).
- **Home widgets:** `.ds-home-widget`, `.ds-home-widget__title`, `.ds-home-widget__row`, `.ds-alert-strip--*`, `.ds-loading-placeholder`.

## 7. Icons

- **Sidebar / headers:** `dashboard/partials/includes/dashboard_icon.html` with `icon_key`.
- Frame: `.dash-header-icon-frame` (colors from `ui-system.css`).

---

## 8. Central file load order (`base.html`)

1. `design-system.css`
2. `motion.css`
3. Tailwind CDN (injects preflight)
4. `design-system.css` (again — wins over Tailwind for tables/forms)
5. `ui-system.css`

`login.html` uses the same stack (without Alpine/HTMX).

**Body typography:** authenticated pages use `<body class="h-full dash-app-body">` — see `.dash-app-body` in `design-system.css` (replaces ad-hoc Tailwind `text-sm` / `antialiased` on `body`).

### Tailwind escape hatches (post-stabilization)

Legacy **zinc/blue attribute substring** bridges in `main` / `header` / `sidebar` were **removed** after templates migrated to `ds-*` / `dash-*`. What remains on purpose:

| Rule | Why keep |
|------|-----------|
| `.dash-app-root [class*="ring-green-500"]` | Optional snippets / focus utilities from Tailwind CDN still emit this token; maps ring to accent. |
| `.dash-app-main main …::placeholder` | Sets placeholder color from `--ds-color-text-placeholder` without depending on utility class names. |
| `aside.dash-app-sidebar > div:first-child:not(.dash-sidebar-brand)` | Layout: non-brand first block matches sidebar chrome. |
| `aside.dash-app-sidebar a[data-nav-tier].is-active` | Active nav glow (not a Tailwind bridge). |

If you reintroduce raw `zinc-*` classes inside `#main-content`, they will **not** be auto-mapped; use design-system classes or tokens instead.

---

## 9. Do / don’t

**Do**

- Add new internal pages with `{% extends "dashboard/base.html" %}`.
- Use `dashboard_page_header` (or `nav_simple` where no icon) for titles.
- Use `ds-*` for forms, buttons, cards, alerts.

**Don’t**

- Change `id="main-content"` or break HTMX `hx-*` on shells.
- Paste large one-off `style=""` blocks.
- Reintroduce raw `zinc-*` / `blue-*` Tailwind utilities for surfaces or type in new templates (no automatic mapping; use `ds-*` or CSS variables).

---

## 10. Future work (incremental)

- Gradually replace repeated Tailwind surface classes in **tracker/tools shells** with `ds-*` wrappers.
- Add `.ds-empty-state` when empty lists are standardized.
- Consider extracting `:root` tokens to `theme.css` only if you need multiple themes later.

---

*Last updated with the unified UI system layer (`ui-system.css`) and chrome-derived palette.*
