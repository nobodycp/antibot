# Antibot dashboard UI system

This document is the **single source of truth** for building and maintaining dashboard UI. It complements the implementation in:

- `dashboard/static/dashboard/css/design-system.css` — tokens + `ds-*` components  
- `dashboard/static/dashboard/css/ui-system.css` — page shell (`.ds-page-shell`), page header layout, auth shell  
- `dashboard/static/dashboard/css/motion.css` — transitions, HTMX enter animations, `prefers-reduced-motion`  
- `dashboard/templates/dashboard/partials/ui/ds_card_head.html` — reusable section header  
- `dashboard/templates/dashboard/partials/includes/dashboard_page_header.html` — page title + icon + optional stats  
- `dashboard/templates/dashboard/partials/includes/dashboard_icon.html` — semantic SVG icons (`icon_key`)

---

## CSS load order: Tailwind CDN and `design-system.css`

Dashboard pages (see `dashboard/templates/dashboard/base.html` and the login template) load **Tailwind from the CDN** first, then **`design-system.css`**, and in some flows **`design-system.css` appears again** after the Tailwind script.

**Why:** Tailwind’s preflight (base reset) runs first. Our **`ds-*`** components and tokens in `design-system.css` are authored to sit **on top of** that baseline. Loading `design-system.css` **again** after the CDN ensures utility classes and any CDN-injected ordering quirks do not leave token-backed surfaces half-styled; it is intentional for consistency, at the cost of an extra network request and duplicate parse until a **local Tailwind build** merges everything into one file.

**Future improvement (optional):** add `tailwind.config.js`, build CSS with `npm run build`, ship a single compiled bundle, and remove the duplicate link — see README / deployment notes when you drop the CDN for stricter CSP or offline installs.

---

## 1. Design tokens

Tokens live in `:root` inside `design-system.css` as `--ds-*` variables.

### 1.1 Color palette (semantic)

| Token / usage | Role |
|---------------|------|
| `--ds-color-bg-app` | App chrome background |
| `--ds-color-bg-raised` | Cards / panels |
| `--ds-color-bg-head` | Card header strip |
| `--ds-color-bg-inset` | Nested groups, fieldsets |
| `--ds-color-bg-field` | Inputs |
| `--ds-color-border`, `--ds-color-border-muted` | Borders |
| `--ds-color-text`, `--ds-color-text-secondary`, `--ds-color-text-muted` | Typography |
| `--ds-color-accent`, `--ds-color-focus-border`, `--ds-color-accent-ring` | Focus / success hints |
| `--ds-color-primary` / hover | Primary filled buttons (chrome-scale surface, not blue) |
| `--ds-color-danger`, `--ds-color-warning`, `--ds-color-success` | Semantic buttons |

**Do:** use `ds-*` classes that consume these tokens.  
**Don’t:** introduce new arbitrary zinc/emerald hex values in templates for the same role.

### 1.2 Spacing scale

`--ds-space-1` … `--ds-space-8` (0.25rem → 2rem). Layout grids may still use Tailwind `gap-*` where a one-off layout is clearer; prefer `ds-card__body` padding for inner rhythm.

### 1.3 Typography

- **Page title:** `dashboard_page_header` (h1 + optional subtitle).  
- **Section kicker:** `.ds-kicker` (uppercase, tracked, muted).  
- **Body:** `.ds-page` sets base `font-size` / line-height.  
- **Table data:** `.ds-table` scales `11px` → `12px` at `sm`.

### 1.4 Radius & borders

- Inputs / small controls: `--ds-radius-md`  
- Cards / fieldsets: `--ds-radius-lg` / `--ds-radius-xl`  
- Card outline + soft ring: implemented on `.ds-card` (shadow + 1px ring).

---

## 2. Components

### 2.1 Page shell

```html
<div class="ds-page">
  {% include "dashboard/partials/includes/dashboard_page_header.html" with ... %}
  ...
</div>
```

Two-column settings layout:

```html
<div class="ds-page-grid">
  <div class="ds-page-grid__main">...</div>
  <div class="ds-page-grid__side">...</div>
</div>
```

### 2.2 Card / panel

```html
<section class="ds-card dash-surface">
  {% include "dashboard/partials/ui/ds_card_head.html" with kicker="Section name" subtitle="Optional description" %}
  <div class="ds-card__body">
    ...
  </div>
</section>
```

- Always pair **`ds-card`** with **`dash-surface`** so hover/motion from `motion.css` applies.  
- **Tables:** `ds-card ds-card--table dash-surface` on the wrapper; inner `<table class="ds-table w-full">`.

### 2.3 Page header (icon + title)

Use `dashboard_page_header.html` with:

- `header_title`, `header_icon` (see §4), optional `header_subtitle`  
- `header_hide_stats=True` when no count  
- Or `heading_items` / `heading_simple_total` / `page_obj` for stats (unchanged contract)

### 2.4 Action bar (compact)

Tracker/tools toolbars: `tracker_shell_actions_card_open.html` / `_close.html` (sticky bar). Keep **HTMX** attributes unchanged on child forms/inputs.

### 2.5 Forms

- Stack: `form.ds-form-stack`  
- Field: `.ds-field` + `.ds-label` + `.ds-input` (or `.ds-select` / `.ds-textarea` when you add those classes)  
- Grouped fields: `.ds-fieldset`  
- Footer actions: `.ds-form-actions` + `.ds-btn …`

Checkboxes in a row: `.ds-check-row` + `.ds-checkbox`.

### 2.6 Buttons

| Class | Use |
|-------|-----|
| `ds-btn ds-btn--primary` | Save, submit main action |
| `ds-btn ds-btn--success` | Confirm / positive secondary |
| `ds-btn ds-btn--warning` | Edit / caution |
| `ds-btn ds-btn--danger` | Delete |
| `ds-btn ds-btn--violet` | Integration / test actions (e.g. Telegram test) |
| `ds-btn ds-btn--amber` | Destructive-adjacent but not delete (e.g. regenerate key) |
| Modifiers: `ds-btn--sm`, `ds-btn--px3` | Compact toolbars |

`<a class="ds-btn …">` is supported (see `design-system.css`).

### 2.7 Tables

- Wrapper: `ds-table-scroll` for horizontal overflow.  
- Table: `ds-table` + width utilities (`min-w-[56rem]` etc.).  
- Header row: plain `<thead><tr><th>…` — **do not** duplicate old `text-[10px] uppercase` Tailwind on every `<th>`; styling comes from CSS.

**Legacy rows:** If a `<tr>` still has `odd:bg-*` utilities, they may override zebra from `.ds-table`; prefer removing row utilities for consistency.

### 2.8 Alerts / messages

`messages_list.html` maps Django levels to:

- `ds-alert ds-alert--success|error|warning|info|default`

Motion: `motion.css` animates `.messages-stack .message`.

---

## 3. Icon system

Defined in `dashboard_icon.html` via **`icon_key`**.

### 3.1 Rules

1. **Semantic only** — pick the key by meaning (blocked IP → `blocked_ip`, not a random glyph).  
2. **Sizes**  
   - Page header frame: default (`h-5 w-5` inside `dash-header-icon-frame`).  
   - Sidebar: `icon_size_class="h-3.5 w-3.5 sm:h-4 sm:w-4"`.  
   - Toolbar: `h-4 w-4` typical.  
3. **Family:** Heroicons-style outline, `stroke-width="2"`, `currentColor`.  
4. **New pages:** add a new `elif` branch with a distinct key; document the key here.

### 3.2 Reference (non-exhaustive)

| `icon_key` | Use |
|------------|-----|
| `profile_user` | Profile |
| `users_team` | Users management |
| `password_lock` | Password / security |
| `backup_settings` | Backup / Telegram |
| `blocked_*`, `log_*`, `ip_info`, `tool_*` | Tracker / tools (see template) |
| `nav_*` | Sidebar section parents |
| `action_refresh` | Toolbar refresh |

---

## 4. Layout rules

- **Main column:** `main` in `base.html` provides horizontal padding; content max width `#main-content` `max-w-[1360px]`.  
- **Between sections:** `space-y-4` / `space-y-5` inside `ds-page`, or `gap` on `ds-page-grid`.  
- **Don’t** nest redundant `rounded-xl border … shadow-lg` on the same node as `ds-card` — the class already encodes the surface.

---

## 5. Do & don’t

### Do

- Build new settings-style pages with `ds-page` → `dashboard_page_header` → `ds-card` + `ds_card_head` → `ds-card__body`.  
- Use `ds-input` / `ds-btn` for form controls and actions.  
- Keep **IDs**, **form `name`s**, **URLs**, and **HTMX** attributes stable when refactoring markup.  
- Link **`design-system.css` before `motion.css`** on any full layout that uses both (see `base.html`).

### Don’t

- Paste long repeated Tailwind strings for inputs/buttons/cards on new pages.  
- Use emoji in section titles — use `ds_kicker` text + page header icons.  
- Change `hx-*`, `name=`, or wrapper IDs such as `*-wrapper` without a functional reason.  
- Add heavy blur/animation on large tables.

---

## 6. Building a new internal page

1. Extend `dashboard/base.html`.  
2. First child of `content`: `<span class="hidden" data-page-title="…">` for the shell title.  
3. Root: `<div class="ds-page">`.  
4. Include **`dashboard_page_header`** with a new **`header_icon`** if needed (add SVG key first).  
5. Body: **`ds-page-grid`** or a single **`ds-card dash-surface`** stack.  
6. Sections: **`ds_card_head`** + **`ds-card__body`**.  
7. Forms: **`ds-form-stack`**, **`ds-fieldset`**, **`ds-field`**, **`ds-input`**, **`ds-form-actions`**, **`ds-btn`**.  
8. Lists/tables: **`ds-card ds-card--table`** + **`ds-table`**.  
9. Verify HTMX targets and pagination partials still point at the same element IDs.

---

## 7. Migration status (rolling)

**Aligned to this system (examples):**  
`change_password.html`, `users_management` shell, `backup` shell, `profile_settings` shell, `home` placeholders, `login.html` (tokens + `ds-*`), `tracker_list_table_open`, tools shells (Google Safe / Redirect / Files tables), `messages_list`.

**Partially legacy (still acceptable):**  
Many tracker **shell** toolbars (compact `h-8` inputs) and **tbody** rows with explicit Tailwind — migrate opportunistically to `ds-input` / strip row utilities when touching a file.

**Documentation:** this file should be updated when adding new `ds-*` primitives or `icon_key` values.
