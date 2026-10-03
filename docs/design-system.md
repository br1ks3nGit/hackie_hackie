# DriveScore Design System

One token set for the insurer dashboard (Jinja2 + HTMX + Alpine + UnoCSS `presetWind`) and the mobile app
(Expo + NativeWind). Class names are Tailwind-compatible. Light theme only (dark mode out of scope for the POC).
Contrast: WCAG 2.2 AA, 4.5:1 body text, 3:1 large text (>= 24px, or >= 18.66px bold) and UI components/graphics.
Ratios below were computed with the WCAG relative-luminance formula.

## 1. Color tokens

### 1.1 Core

| Token (theme key) | Hex | Use |
|---|---|---|
| `primary` (DEFAULT) | #0062CC | Buttons, links, active nav, focus accents. Matches current mobile. |
| `primary-hover` | #0052A8 | Hover (web) |
| `primary-active` | #00428A | Pressed (web and mobile) |
| `primary-fg` | #FFFFFF | Text/icon on primary |
| `surface` | #FFFFFF | Page cards, inputs, app background |
| `surface-muted` | #F3F4F6 | Page background (dashboard), table header, zebra, skeleton, mobile card |
| `border` | #D1D5DB | Decorative dividers, card outline (not an input boundary) |
| `border-strong` | #6B7280 | Input / select / checkbox boundary (needs 3:1) |
| `text` | #111827 | Body, headings |
| `text-muted` | #4B5563 | Secondary text, captions, table headers |
| `nav` | #111827 | Dashboard top bar background |
| `nav-fg` | #E5E7EB | Nav link text on `nav` (active link uses #FFFFFF) |

### 1.2 Status (each has DEFAULT = solid/text-on-white, `soft` = tinted bg, `ink` = text on soft)

| Key | DEFAULT | soft | ink |
|---|---|---|---|
| `success` | #15803D | #DCFCE7 | #166534 |
| `warning` | #B45309 | #FEF3C7 | #92400E |
| `danger` | #B91C1C | #FEE2E2 | #991B1B |
| `info` | #1D4ED8 | #DBEAFE | #1E40AF |

`danger` DEFAULT also is the fill of the danger button (white text, 6.47:1).

### 1.3 Tier colors (A best, E worst)

Tier is ALWAYS shown as the letter plus color (badge reads "A", chart axis labels read "A".."E", legend text, table cell text).
DEFAULT = solid (chart bars, score ring, white text on it passes). `soft` + `ink` = badge tint.

| Key | DEFAULT | soft | ink | Hue |
|---|---|---|---|---|
| `tier-a` | #15803D | #DCFCE7 | #14532D | green |
| `tier-b` | #4D7C0F | #ECFCCB | #365314 | lime |
| `tier-c` | #A16207 | #FEF08A | #713F12 | amber |
| `tier-d` | #C2410C | #FFEDD5 | #7C2D12 | orange |
| `tier-e` | #B91C1C | #FEE2E2 | #7F1D1D | red |

Tier from `values.Tier` = "A".."E". Unscored (null tier) uses `surface-muted` bg, `text-muted` text, label "n/a".

### 1.4 Event-type colors (event list chips; map markers removed for privacy)

Chips differ by glyph (not color alone). Map markers were removed for privacy (no locations are stored or shown).

| Key | Hex | Value in `values.EventType` | Marker shape | Label |
|---|---|---|---|---|
| `event-harsh-brake` | #C2410C | `harsh_brake` | circle, "Br" | Harsh brake |
| `event-harsh-accel` | #7E22CE | `harsh_accel` | circle, "Ac" | Harsh acceleration |
| `event-sharp-corner` | #0E7490 | `sharp_corner` | circle, "Co" | Sharp corner |
| `event-speeding` | #B91C1C | `speeding` | circle, "Sp" | Speeding |
| `event-crash` | #111827 | `crash` (incident marker; not in EventType) | square, "!" | Crash |

Marker and route polyline specs: removed for privacy.
Glyphs are 2 letters (11px bold) so they never read as tier letters A-E.

### 1.5 Contrast table (all pairs used)

| Foreground on background | Ratio | Needs | Pass |
|---|---|---|---|
| text #111827 on surface | 17.74 | 4.5 | yes |
| text on surface-muted | 16.12 | 4.5 | yes |
| text-muted #4B5563 on surface | 7.56 | 4.5 | yes |
| text-muted on surface-muted | 6.87 | 4.5 | yes |
| primary-fg on primary #0062CC | 5.80 | 4.5 | yes |
| primary-fg on primary-hover | 7.57 | 4.5 | yes |
| primary-fg on primary-active | 9.78 | 4.5 | yes |
| primary (link/text) on surface | 5.80 | 4.5 | yes |
| primary on surface-muted | 5.27 | 4.5 | yes |
| border-strong #6B7280 on surface (input edge) | 4.83 | 3 | yes |
| border #D1D5DB on surface | 1.47 | decorative only | n/a, never sole boundary of a control |
| white on danger #B91C1C | 6.47 | 4.5 | yes |
| danger on surface (error text) | 6.47 | 4.5 | yes |
| success ink on soft (#166534/#DCFCE7) | 6.49 | 4.5 | yes |
| warning ink on soft (#92400E/#FEF3C7) | 6.37 | 4.5 | yes |
| danger ink on soft (#991B1B/#FEE2E2) | 6.80 | 4.5 | yes |
| info ink on soft (#1E40AF/#DBEAFE) | 7.15 | 4.5 | yes |
| success #15803D on surface | 5.02 | 4.5 | yes |
| warning #B45309 on surface | 5.02 | 4.5 | yes |
| info #1D4ED8 on surface | 6.70 | 4.5 | yes |
| tier-a ink on soft (#14532D/#DCFCE7) | 8.30 | 4.5 | yes |
| tier-b ink on soft (#365314/#ECFCCB) | 8.05 | 4.5 | yes |
| tier-c ink on soft (#713F12/#FEF08A) | 7.45 | 4.5 | yes |
| tier-d ink on soft (#7C2D12/#FFEDD5) | 8.18 | 4.5 | yes |
| tier-e ink on soft (#7F1D1D/#FEE2E2) | 8.20 | 4.5 | yes |
| tier solid A/B/C/D/E on surface (bars, ring) | 5.02 / 4.99 / 4.92 / 5.18 / 6.47 | 3 (graphics), 4.5 (text) | yes |
| white on tier solid A/B/C/D/E | 5.02 / 4.99 / 4.92 / 5.18 / 6.47 | 4.5 | yes |
| tier solids on surface-muted | >= 4.47 | 3 | yes |
| event colors on surface: brake / accel / corner / speeding / crash | 5.18 / 6.98 / 5.36 / 6.47 / 17.74 | 3 | yes |
| white glyph on event colors | same ratios as above | 4.5 (small glyph) | yes |
| nav-fg #E5E7EB on nav #111827 | 14.33 | 4.5 | yes |
| white on nav | 17.74 | 4.5 | yes |
| focus ring #1D4ED8 on surface / surface-muted | 6.70 / 6.09 | 3 | yes |

Rules: never use `text-muted` on tinted `soft` backgrounds (use the `ink` color). Never put `primary` text on `nav`.
Disabled controls are exempt from contrast but must not be the only state signal (also `cursor-not-allowed`, `aria-disabled`).

## 2. Foundations

### 2.1 Typography

Font stack (no downloads):
- Sans: `ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif`
- Mono (ids, g values): `ui-monospace, SFMono-Regular, Menlo, Consolas, monospace`
- Mobile: omit custom family (platform system font); size values below apply 1:1 as pt.

| Token | Size | Line height | Weight | Use |
|---|---|---|---|---|
| `text-xs` | 12px / 0.75rem | 16px | 500 | Legend, badge, caption (not for body) |
| `text-sm` | 14px / 0.875rem | 20px | 400 | Table cells, helper, secondary |
| `text-base` | 16px / 1rem | 24px | 400 | Body, inputs (16px prevents iOS zoom) |
| `text-lg` | 18px / 1.125rem | 28px | 600 | Card title |
| `text-xl` | 20px / 1.25rem | 28px | 600 | Section heading (h2) |
| `text-2xl` | 24px / 1.5rem | 32px | 700 | Page title (h1) |
| `text-3xl` | 30px / 1.875rem | 36px | 700 | Stat tile value |
| `text-5xl` | 48px / 3rem | 48px | 700 | Mobile score number (matches current 48) |

Weights: 400 body, 500 labels, 600 headings, 700 titles/values. These equal Tailwind defaults; no override needed except
mobile where sizes are explicit. Use `rem` on web so browser font scaling works; mobile text must not set `allowFontScaling={false}`.

### 2.2 Spacing (4px base; Tailwind defaults)

`1`=4px, `2`=8px, `3`=12px, `4`=16px, `5`=20px, `6`=24px, `8`=32px, `10`=40px, `12`=48px, `16`=64px.
Page padding: 16px (<640px), 24px (>=640px). Card padding: 16px mobile / 24px desktop. Stack gap inside cards: 12px.
Min target size: 44x44 on mobile, 40px high controls on web (>= 24x24 WCAG minimum).

### 2.3 Radii

`rounded-sm` 4px (badge, chip inner), `rounded` / `rounded-md` 8px (buttons, inputs; matches mobile 8), `rounded-lg` 12px (cards, tiles),
`rounded-full` 9999px (pills, switch). Mobile card radius currently 10: change to 12 (`rounded-lg`).

### 2.4 Shadows (web)

- `shadow-sm`: `0 1px 2px 0 rgb(17 24 39 / 0.06)` card rest
- `shadow-md`: `0 4px 8px -2px rgb(17 24 39 / 0.12)` dropdown, toast
Mobile: no shadows (use 1px `border`).

### 2.5 Breakpoints (dashboard; Tailwind defaults)

`sm` 640px, `md` 768px, `lg` 1024px, `xl` 1280px. Design mobile-first, verify at 360px with no horizontal page scroll.
Content max width: `max-w-6xl` (1152px) centered.

### 2.6 Focus-visible

Web: `focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus focus-visible:ring-offset-2`
(2px ring #1D4ED8, 2px offset white; shortcut `kbd-focus`). Never remove focus without replacement. On `nav` bar links use
`focus-visible:ring-white focus-visible:ring-offset-nav`.
Mobile: no keyboard focus; rely on pressed state (`active:bg-primary-active`) and TalkBack/VoiceOver focus.
Color token: `focus` = #1D4ED8.

### 2.7 Motion

Durations: 150ms (hover, press), 200ms (toast, expand). Easing: `cubic-bezier(0.2, 0, 0, 1)`. Honor `prefers-reduced-motion`
(`motion-reduce:transition-none motion-reduce:animate-none`). Skeleton pulse: `animate-pulse`.

## 3. Components

Dashboard components are Jinja macros in `backend/app/templates/components/` using these shortcuts (defined in `uno.config.ts`).
Class strings must appear literally in templates.

### 3.1 Button (`btn`)

Base: `inline-flex items-center justify-center gap-2 rounded-md font-medium text-base min-h-10 px-4 kbd-focus transition-colors duration-150 disabled:opacity-50 disabled:cursor-not-allowed`

| Variant | Classes | Hover / active |
|---|---|---|
| primary | `bg-primary text-primary-fg` | `hover:bg-primary-hover active:bg-primary-active` |
| secondary | `bg-surface text-primary border border-primary` | `hover:bg-surface-muted active:bg-surface-muted` |
| danger | `bg-danger text-white` | `hover:bg-danger-ink active:bg-danger-ink` |

Sizes: `sm` = `min-h-8 px-3 text-sm` (still >= 24px), `md` (default) = `min-h-10 px-4`, `lg` = `min-h-12 px-6`.
Disabled: `disabled` attribute (not just a class) + opacity 50%. Loading: HTMX `hx-disabled-elt="this"` plus an inline spinner
(`<span class="htmx-indicator i-spinner animate-spin" aria-hidden="true">`) and `aria-busy="true"`; keep label text so width does not jump.
Icon-only: needs `aria-label`, min 40x40.
Use `<button>` for actions, `<a class="btn ...">` for navigation.

### 3.2 Input, label, error (`field`)

```
<div class="flex flex-col gap-1">
  <label for="username" class="text-sm font-medium text-text">Username</label>
  <input id="username" class="input" aria-describedby="username-hint username-err" ...>
  <p id="username-hint" class="text-sm text-text-muted">...</p>
  <p id="username-err" class="text-sm text-danger" role="alert">Error text</p>   <!-- only when invalid -->
</div>
```
`input`: `w-full min-h-10 px-3 rounded-md bg-surface text-text text-base border border-border-strong placeholder:text-text-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus focus-visible:border-primary`
Error state: add `border-danger aria-[invalid=true]:border-danger` and set `aria-invalid="true"`; error text prefixed by an icon or the word "Error:" (not color alone).
Disabled: `disabled:bg-surface-muted disabled:text-text-muted disabled:cursor-not-allowed`.
Required: label shows "(required)" text, `required` attribute. Placeholder is never the label.

### 3.3 Select

Native `<select class="input pr-8">` (keeps keyboard and mobile pickers). Label as above. Used for tier filter (options: All, A, B, C, D, E) and sort
(Score, Multiplier). Auto-submit with `hx-get` + `hx-trigger="change"`; also a visible "Apply" button inside `<noscript>`.

### 3.4 Card

`bg-surface rounded-lg border border-border shadow-sm p-4 md:p-6`. Optional header: `text-lg font-semibold text-text` as h2/h3.
Not clickable by default; a clickable card is an `<a>` wrapping, with `kbd-focus hover:shadow-md`.

### 3.5 Stat tile

Card with: label (`text-sm text-text-muted`), value (`text-3xl font-bold text-text`), optional hint (`text-xs text-text-muted`).
Use `<dl>` : `<dt>` label, `<dd>` value. Grid: `grid grid-cols-1 sm:grid-cols-3 gap-4`. Multiplier value shown as `1.15x`.
Loading: three skeleton bars. Null data: `<dd>-<span class="sr-only">No data</span></dd>`.

### 3.6 Table

Wrapper: `overflow-x-auto rounded-lg border border-border bg-surface` with `tabindex="0" role="region" aria-label="<name>"` so wide tables scroll inside.
`<table class="w-full text-sm text-left">`, `<caption class="sr-only">`, header `bg-surface-muted text-text-muted font-medium`,
`th` `px-4 py-3`, `td` `px-4 py-3 border-t border-border`, row hover `hover:bg-surface-muted`.
Sortable header: `<th aria-sort="ascending|descending|none">` containing a `<button class="inline-flex items-center gap-1 kbd-focus">Score <span aria-hidden>arrow</span></button>`
(`hx-get` with `sort` and `dir` params, `hx-target="#drivers-table"`). Active sort shows an arrow glyph plus `aria-sort`; not color only.
Numeric columns right-aligned with `tabular-nums`. Driver id cells use mono and link to detail.
Empty state: single `<tr><td colspan>` containing the empty-state component ("No drivers match this filter" + "Clear filter" secondary button).
Pagination (`<nav aria-label="Pagination">`): "Showing 21-40 of 133" (`text-sm text-text-muted`), Previous / Next secondary `sm` buttons
(`aria-disabled="true"` + `disabled` on the ends), current page text "Page 2 of 7". Links use `hx-get`, `hx-target` the table partial, `hx-push-url="true"`.

### 3.7 Tier badge (`tier-badge`)

Sortable table headers are real links (`href` works without JS; HTMX enhances them) with sr-only text for the action. Tier badge pattern: visible letter `aria-hidden="true"` plus `<span class="sr-only">Tier A</span>` (no `aria-label` on the span).

`inline-flex items-center gap-1 rounded-sm px-2 py-0.5 text-xs font-semibold` + `bg-tier-a-soft text-tier-a-ink` (per tier).
Content: letter always visible: `<span aria-hidden="true">A</span><span class="sr-only">Tier A</span>`
(no `aria-label` on a role-less span); larger variant `lg` = `text-base px-3 py-1`. Score ring/bars use
solid `bg-tier-x` with the letter printed next to them.
Dynamic tier classes: map tier->class literally in the macro (a dict of full class strings), never string-build `bg-tier-` + letter
(or add them to the UnoCSS `safelist`; coder must safelist all tier/status/event classes).

### 3.8 Status pill (`pill`)

`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium` + leading dot/glyph + text. Always text.

| Domain value | Label | Classes |
|---|---|---|
| trip `done` | Done | `bg-success-soft text-success-ink` |
| trip `processing` | Processing | `bg-info-soft text-info-ink` |
| trip `uploading` | Uploading | `bg-info-soft text-info-ink` |
| trip `failed` | Failed | `bg-danger-soft text-danger-ink` |
| incident `ok` | Driver OK | `bg-success-soft text-success-ink` |
| incident `help_needed` | Help needed | `bg-danger-soft text-danger-ink` |
| incident `no_response` | No response | `bg-warning-soft text-warning-ink` |
| incident null (pending) | Awaiting response | `bg-surface-muted text-text` |
| passenger share flag (`flagged_for_review`) | Review | `bg-warning-soft text-warning-ink` |

Glyph prefix (text, aria-hidden): done "ok", failed "x", help "!", etc., or small inline SVG.

### 3.9 Nav bar

`<header class="bg-nav text-nav-fg">` with `<nav aria-label="Main">`: brand "DriveScore" (white, font-semibold) left;
links Overview, Drivers, Incidents; Sign out as a `<form method="post" action="/dashboard/logout">` with CSRF input and a ghost button on the right.
Link: `px-3 py-2 rounded-md text-sm font-medium text-nav-fg hover:text-white hover:bg-white/10 kbd-focus`; active adds `text-white bg-white/15` and `aria-current="page"`.
<640px: links wrap onto a second row (no hamburger; 3 links fit in 360px at `px-3`). Include "Skip to main content" link (`sr-only focus:not-sr-only`) as first focusable element.
Page content in `<main id="main" class="mx-auto max-w-6xl p-4 sm:p-6">`.

### 3.10 Flash / toast

Inline flash (login errors, form results): `rounded-md border px-4 py-3 text-sm flex gap-2` with variant `bg-{status}-soft text-{status}-ink border-{status}`
and leading text label ("Error:", "Success:", "Note:"). Container `role="status" aria-live="polite"`; errors use `role="alert"`.
Toast (HX-Trigger `showToast`): fixed `bottom-4 right-4 left-4 sm:left-auto sm:w-96`, `shadow-md`, auto-dismiss 6s (errors persist), dismiss button `aria-label="Dismiss"`,
region `aria-live="polite"` rendered once in base.html. Pause dismiss on hover/focus.

### 3.11 Empty state

Centered in card: title `text-lg font-semibold`, hint `text-sm text-text-muted`, optional secondary button; `py-12 text-center`.
Copy: Drivers "No drivers yet. Scored trips will appear here."; Incidents "No incidents recorded."; Trip events "No events detected on this trip."

### 3.12 Loading skeleton

`bg-surface-muted rounded animate-pulse` blocks sized like the content (tile: `h-24`, table row: `h-10`). Container `aria-busy="true"`; add `sr-only` "Loading".
HTMX: `hx-indicator` on a skeleton or spinner with class `htmx-indicator` (opacity 0, shown when `.htmx-request`). Reduced motion: no pulse.

### 3.13 Map legend

Removed for privacy: the dashboard has no map, legend or location display.

### 3.14 Chart (tier distribution, Chart.js)

Bar chart, one bar per tier A..E in tier solid colors, x-axis labels "A".."E", y-axis count, value labels on bars (Chart.js datalabels or tooltips only is NOT enough).
Provide a visually-hidden or toggled data table `<table class="sr-only">` (Tier, Scored trips) as text alternative; canvas `role="img" aria-label="Scored trips per tier: A 10, B 20, ..."`.
Grid lines `border` color, tick text `text-muted` 12px. Size `h-64`.

## 4. Mobile components (NativeWind; match E2/E3 in `mobile/App.tsx`)

Use token class names; pressed state is `active:` variant or `Pressable` style callback. All touchables: `accessibilityRole`, `accessibilityLabel`, min 44x44.
Screen: `flex-1 bg-surface px-5 pt-[60px]` -> use `px-5 pt-4` (16px) inside a `SafeAreaView`; the safe area supplies the status-bar inset, so do not use `pt-16`.

| Component | Classes / spec |
|---|---|
| Title | `text-3xl font-bold text-text` (was 28) |
| Score card | `bg-surface-muted rounded-lg p-4`; label `text-sm text-text-muted`; score `text-5xl font-bold text-text` with tier chip next to it; multiplier `text-base text-text`; trend text word ("Improving") with arrow glyph. Number uses `text` color (not tier color) so contrast holds; tier is the chip. Existing `#007AFF` score text is below 4.5:1 on #f2f2f7 (about 3.6:1), so it must change to `text-text`. |
| Tier chip | `rounded-sm px-2 py-0.5 text-xs font-semibold bg-tier-x-soft text-tier-x-ink`, letter always shown, `accessibilityLabel="Tier A"` |
| Switch row ("I'm driving") | `flex-row items-center justify-between min-h-12 py-2`; label `text-base text-text`, caption `text-sm text-text-muted`; RN `Switch` `trackColor={{true: primary, false: border-strong}}` (RN props take hex, so the track colors are mirrored in `mobile/src/tokens.ts`; change both places when `primary` or `border-strong` changes), `accessibilityRole="switch"`, `accessibilityState={{checked}}`; the whole row is the label. Restate state in text ("On: trips are labelled as driving"). |
| Recording status | Banner `rounded-lg p-4`: recording `bg-success-soft` + `text-success-ink` text "Recording trip" with dot; idle `bg-surface-muted text-text`. Always visible while recording. Replaces current `#e5f5e5` / `#fff4e0` banners (warning variant `bg-warning-soft text-warning-ink`). |
| Banner (error/info) | `rounded-lg p-4` + `bg-{danger,info,warning}-soft` text `{x}-ink` with prefix word ("Error:", "Saved:"); `accessibilityLiveRegion="polite"` and `AccessibilityInfo.announceForAccessibility` as now. |
| List row (trip to confirm) | `bg-surface-muted rounded-lg p-4 gap-3`; title `text-base font-semibold text-text` (time, distance km), meta `text-sm text-text-muted` (transit line / score + tier chip), buttons in `flex-row gap-2` (stack to `flex-col` when `fontScale > 1.3`, existing logic). Buttons are `flex-1` only in the row layout; when stacked they are full width without `flex-1` (flex-1 in a column collapses height at large font). |
| Trips-to-confirm container | Wrapper `bg-warning-soft rounded-lg p-4 gap-3` with a heading `text-base font-semibold text-warning-ink`; each trip row inside is a `bg-surface rounded-lg p-4 gap-3` list row (surface rows on the warning-soft container, so row text uses `text-text` / `text-text-muted`, not `ink`). |
| Summary card | `bg-surface-muted rounded-lg p-4 gap-2`; explanation sentence `text-base text-text-muted`; event lines (one per event type, e.g. "3 harsh brakes") `text-sm text-text-muted`. Text only, no color-coding; used for the post-trip summary and the score explanation. |
| Primary button | `min-h-11 rounded-md px-3 items-center justify-center bg-primary active:bg-primary-active`; text `text-base font-semibold text-primary-fg`. Disabled `opacity-50`. |
| Secondary button | `min-h-11 rounded-md px-3 items-center justify-center bg-surface border border-primary active:bg-surface-muted`; text `text-base font-semibold text-primary`. |
| Loading | `ActivityIndicator color=primary` + text "Loading..." ; skeleton `bg-surface-muted rounded-lg h-20`. |
| Empty | `text-base text-text-muted` centered: "No trips to confirm." |

## 5. Page layouts (dashboard)

All routes under `/dashboard`, require staff session; full pages render `base.html` (nav + `<main id="main">` + toast region + `<body hx-headers='{"X-CSRF-Token": "..."}'>`).
Fragment routes return partials from `app/templates/partials/` (detected via `HX-Request`). Data via `app/services/` (same data as the JSON schemas named below), not by calling the JSON API.

### F1 Login + base layout
- `GET /dashboard/login`: centered card `max-w-sm mx-auto mt-16`, h1 "DriveScore Insurer", fields username and password (`field`), primary `lg` button "Sign in" (full width), flash for errors (role=alert, "Invalid username or password"; do not say which). Plain form POST with CSRF (no HTMX needed). 422/401 re-render the form with error.
- No nav shown when logged out. `base.html`: skip link, nav (3.9), main, toast region, static JS (htmx, alpine, chart.js) pinned, `uno.css`.

### F2 Overview (`GET /dashboard`) - schema `InsurerOverviewResponse`
- h1 "Overview". 3 stat tiles: Total drivers (`total_drivers`), Trips in last 90 days (`total_trips_90d`), Average premium multiplier (`average_multiplier`, "1.15x").
- Card "Tier distribution" ("Scored trips per tier", table column "Scored trips"): bar chart (3.14) from `tier_distribution`, JSON in `<script type="application/json" id="tier-data">`, Alpine component re-inits on `htmx:afterSwap`. Missing tiers = 0.
- Partial `partials/overview_stats.html` (tiles + chart data) with `hx-trigger="every 30s"`, `hx-swap="outerHTML"`, stable id `#overview-stats`.

### F3 Drivers (`GET /dashboard/drivers`) - `InsurerDriverItem`; detail `GET /dashboard/drivers/{driver_id}` - `InsurerDriverDetailResponse`
- List: filter bar in card (select Tier, select Sort, direction toggle), table (3.6) columns: Driver (link), Score, Tier (badge), Multiplier, Trips (90d), Distance km (90d). Page size 20.
- Partial `partials/drivers_table.html` (filter bar stays outside; table + pagination inside `#drivers-table`); filter/sort/page requests `hx-get` to the same URL, `hx-push-url="true"`, `aria-live="polite"` result count line "133 drivers".
- Detail: breadcrumb link back to Drivers; header: id (mono), tier badge lg, flagged pill if `flagged_for_review`; stat tiles: Score, Multiplier, Passenger share (`passenger_share` as %, with pill "Review" when flagged); card "Events" as `<dl>` counts from `event_rates` (label per EventType, with event color swatch + text); card "Label sources" (small `<dl>` from `label_sources`); card "Recent trips" table of `trips` (Started, Distance, Score, Tier, Type, Status) rows link to F4. Whole page (no partials needed).

### F4 Trip detail (`GET /dashboard/trips/{trip_id}`) - `TripDetailResponse`
- Header: started time, duration_min, distance_km, tier badge, score, confidence ("Confidence 85%").
- Map card: removed for privacy (no route or locations).
- Event list card: table or `<ul>` (time, type label with swatch, peak g). Empty state if no events.
- "Why this score" card: `explanation` paragraph, `text-base`; null -> "No explanation available."
- Trip not scored (`tier` null) -> status pill + message; `failed` shows `failure_reason` in a danger flash. Full page.

### F5 Incidents (`GET /dashboard/incidents`)
- Table: Time (local, ISO in `<time datetime>`), Driver (link), Peak g (`2.4 g`, mono), Confirmation (status pill 3.8). Newest first, pagination as 3.6.
- Partial `partials/incidents_table.html` polling `hx-trigger="every 30s"` (aria-live off for poll to avoid chatter; announce only new count via `HX-Trigger`).
- Empty state "No incidents recorded."

## 6. Token names (identical in both configs)

Both configs use these exact keys. `DEFAULT` gives the bare class (`bg-primary`). Hyphenated variants are written as nested keys.

```
colors: {
  primary:  { DEFAULT: '#0062CC', hover: '#0052A8', active: '#00428A', fg: '#FFFFFF' },
  surface:  { DEFAULT: '#FFFFFF', muted: '#F3F4F6' },
  border:   { DEFAULT: '#D1D5DB', strong: '#6B7280' },
  text:     { DEFAULT: '#111827', muted: '#4B5563' },
  nav:      { DEFAULT: '#111827', fg: '#E5E7EB' },
  focus:    '#1D4ED8',
  success:  { DEFAULT: '#15803D', soft: '#DCFCE7', ink: '#166534' },
  warning:  { DEFAULT: '#B45309', soft: '#FEF3C7', ink: '#92400E' },
  danger:   { DEFAULT: '#B91C1C', soft: '#FEE2E2', ink: '#991B1B' },
  info:     { DEFAULT: '#1D4ED8', soft: '#DBEAFE', ink: '#1E40AF' },
  tier: {
    a: { DEFAULT: '#15803D', soft: '#DCFCE7', ink: '#14532D' },
    b: { DEFAULT: '#4D7C0F', soft: '#ECFCCB', ink: '#365314' },
    c: { DEFAULT: '#A16207', soft: '#FEF08A', ink: '#713F12' },
    d: { DEFAULT: '#C2410C', soft: '#FFEDD5', ink: '#7C2D12' },
    e: { DEFAULT: '#B91C1C', soft: '#FEE2E2', ink: '#7F1D1D' },
  },
  event: {
    'harsh-brake': '#C2410C', 'harsh-accel': '#7E22CE', 'sharp-corner': '#0E7490',
    speeding: '#B91C1C', crash: '#111827',
  },
}
```

| Config | Where | Notes |
|---|---|---|
| UnoCSS | `backend/uno.config.ts` -> `theme.colors` (presetWind; nested objects are supported) | Also `theme.fontFamily.sans/mono`, `theme.boxShadow` (`sm`, `md` from 2.4), `theme.ringColor`/colors `focus`. `shortcuts`: `btn`, `btn-primary`, `btn-secondary`, `btn-danger`, `btn-sm`, `btn-lg`, `input`, `kbd-focus`, `card`, `pill`, `tier-badge`. `safeList` all `tier-*`, `{status}-soft/ink`, `event-*` classes. |
| NativeWind | `mobile/tailwind.config.js` -> `theme.extend.colors` | Same object, no `nav`/`focus`/`event` needed (harmless if kept). Radii/spacing/sizes use Tailwind defaults (match section 2). Content globs `./App.tsx`, `./src/**/*.{ts,tsx}`; preset `nativewind/preset`. Use hex strings only (no `rgb(var())`). |

Chart.js reads the same hex values: coder exposes them to JS by copying from the Python-side constants or reading CSS vars; simplest is to hard-code the
tier/event hex in one static JS module `static/js/tokens.js` that mirrors section 6 (comment it as mirror).

## 7. Do / Don't

- Do show tier as letter + color; show status as text + color; show event type as glyph + color.
- Do use `ink` colors on `soft` backgrounds; `text-muted` only on `surface`/`surface-muted`.
- Do use `<button>`, `<a>`, `<label>`, `<table>`; keep one `<h1>` per page.
- Don't use arbitrary values (`text-[#123]`, `p-[13px]`); add a token first.
- Don't use `border` (#D1D5DB) as the only boundary of an input.
- Don't build class names by string concat; use full literal strings or safelist.
- Don't hard-code hex or font sizes in `mobile/` screens; use the token class names.
- Don't rely on hover; every hover action has a focus or tap equivalent.
