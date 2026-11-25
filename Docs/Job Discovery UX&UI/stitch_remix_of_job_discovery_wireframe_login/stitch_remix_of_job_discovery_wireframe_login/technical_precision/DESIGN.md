---
name: Technical Precision
colors:
  surface: '#faf8ff'
  surface-dim: '#d9d9e5'
  surface-bright: '#faf8ff'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#f3f3fe'
  surface-container: '#ededf9'
  surface-container-high: '#e7e7f3'
  surface-container-highest: '#e1e2ed'
  on-surface: '#191b23'
  on-surface-variant: '#434655'
  inverse-surface: '#2e3039'
  inverse-on-surface: '#f0f0fb'
  outline: '#737686'
  outline-variant: '#c3c6d7'
  surface-tint: '#0053db'
  primary: '#004ac6'
  on-primary: '#ffffff'
  primary-container: '#2563eb'
  on-primary-container: '#eeefff'
  inverse-primary: '#b4c5ff'
  secondary: '#565e74'
  on-secondary: '#ffffff'
  secondary-container: '#dae2fd'
  on-secondary-container: '#5c647a'
  tertiary: '#943700'
  on-tertiary: '#ffffff'
  tertiary-container: '#bc4800'
  on-tertiary-container: '#ffede6'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#dbe1ff'
  primary-fixed-dim: '#b4c5ff'
  on-primary-fixed: '#00174b'
  on-primary-fixed-variant: '#003ea8'
  secondary-fixed: '#dae2fd'
  secondary-fixed-dim: '#bec6e0'
  on-secondary-fixed: '#131b2e'
  on-secondary-fixed-variant: '#3f465c'
  tertiary-fixed: '#ffdbcd'
  tertiary-fixed-dim: '#ffb596'
  on-tertiary-fixed: '#360f00'
  on-tertiary-fixed-variant: '#7d2d00'
  background: '#faf8ff'
  on-background: '#191b23'
  surface-variant: '#e1e2ed'
typography:
  headline-xl:
    fontFamily: Inter
    fontSize: 36px
    fontWeight: '600'
    lineHeight: 44px
    letterSpacing: -0.025em
  headline-xl-mobile:
    fontFamily: Inter
    fontSize: 28px
    fontWeight: '600'
    lineHeight: 36px
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: Inter
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
    letterSpacing: -0.02em
  headline-md:
    fontFamily: Inter
    fontSize: 20px
    fontWeight: '600'
    lineHeight: 28px
    letterSpacing: -0.015em
  headline-sm:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '600'
    lineHeight: 24px
    letterSpacing: -0.01em
  body-lg:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 26px
    letterSpacing: -0.005em
  body-md:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 22px
    letterSpacing: 0em
  body-sm:
    fontFamily: Inter
    fontSize: 13px
    fontWeight: '400'
    lineHeight: 18px
    letterSpacing: 0em
  label-md:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '500'
    lineHeight: 16px
    letterSpacing: 0.02em
  label-sm:
    fontFamily: Inter
    fontSize: 11px
    fontWeight: '600'
    lineHeight: 14px
    letterSpacing: 0.04em
  code-sm:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '500'
    lineHeight: 16px
    letterSpacing: -0.01em
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  gutter: 1rem
  gutter-lg: 1.5rem
  margin: 1rem
  margin-md: 1.5rem
  margin-lg: 2rem
  space-2xs: 0.125rem
  space-xs: 0.25rem
  space-sm: 0.5rem
  space-md: 0.75rem
  space-lg: 1rem
  space-xl: 1.5rem
  space-2xl: 2rem
  space-3xl: 3rem
---

## Brand & Style
The design system targets software engineers, product designers, technical leaders, and modern builders looking for their next high-impact career move. The identity prioritizes speed, high-density data legibility, and no-nonsense utility, channeling the engineering-first aesthetic of platforms like Linear and Vercel.

The emotional tone balances surgical precision, calm focus, and effortless efficiency. The UI avoids unnecessary ornamentation, decorative gradients, and visual noise, treating job search and evaluation like an optimized developer workflow. The design movement is modern minimalist SaaS: crisp hairline borders, disciplined neutral slate surfaces, strict typographic hierarchy, and intentional technical blue highlights.

## Colors
The color system operates on high-contrast slate neutrals anchored by a vibrant technical blue.

- **Primary (`#2563EB`)**: Used exclusively for direct focal actions (primary CTA buttons, active tab indicators, focused inputs, interactive badge highlights).
- **Secondary / Headings (`#0F172A`)**: Deep slate charcoal reserved for primary headings, critical metrics, and emphasized titles.
- **Body & Secondary Copy (`#1E293B` and `#64748B`)**: `#1E293B` ensures comfortable reading contrast for body text, while muted slate (`#64748B`) drives secondary metadata, timestamps, tags, and label headers.
- **Canvas & Containers**: The default canvas utilizes cool light gray (`#F8FAFC`), while cards, modals, and raised surfaces sit on pure white (`#FFFFFF`) to establish crisp structural separation.
- **Borders & Dividers (`#E2E8F0`)**: Hairline dividers and surface borders define layout structure without overwhelming the content.

## Typography
Typography is set purely in Inter, tuned with negative tracking on medium and large display roles to achieve the crisp, dense feel characteristic of modern developer tools. 

Vertical rhythm relies on tight, proportional line heights that maximize screen density without compromising scanning velocity. Labels and small tags use medium-to-semibold weights with subtle positive tracking to maintain clear legibility at 11px and 12px scales.

## Layout & Spacing
The layout operates on an 8pt base grid with an embedded 4pt sub-grid for internal component alignment, padding, and micro-spacing.

- **Breakpoints**: Mobile (<768px), Tablet (768px–1024px), Desktop (>1024px).
- **Layout Architecture**: 
  - Desktop uses a 12-column fluid grid system bounded by a max width of 1280px or 1440px with a persistent left navigation rail/filter drawer.
  - Tablet condenses secondary sidebars into collapsibles with a 1.5rem outer canvas margin.
  - Mobile drops into a single-column layout with 1rem edge padding and fixed horizontal filter chips.
- Spacing density is compact: inputs, table rows, and list items maintain a lean vertical footprint to prioritize content visibility per viewport.

## Elevation & Depth
Depth is constructed through subtle perimeter borders and restrained, micro-blur drop shadows rather than heavy blurs or stacked layers.

- **Level 0 (Flat / Canvas)**: `#F8FAFC` base background with zero elevation.
- **Level 1 (Card / Container)**: Pure white background (`#FFFFFF`) framed with a 1px solid border in `#E2E8F0`. Shadow: `0 1px 2px 0 rgba(15, 23, 42, 0.04)`.
- **Level 2 (Hover / Active Rows)**: Slight lift for interactive cards on pointer hover. Shadow: `0 4px 6px -1px rgba(15, 23, 42, 0.06), 0 2px 4px -2px rgba(15, 23, 42, 0.04)`. Border shifts to `#CBD5E1`.
- **Level 3 (Dropdowns / Menus / Popovers)**: `#FFFFFF` floating panels with border `#E2E8F0` and shadow: `0 10px 15px -3px rgba(15, 23, 42, 0.08), 0 4px 6px -4px rgba(15, 23, 42, 0.04)`.
- **Level 4 (Modals & Command Palettes)**: Centered overlays accompanied by a translucent backdrop (`rgba(15, 23, 42, 0.4)` with 4px backdrop blur). Shadow: `0 20px 25px -5px rgba(15, 23, 42, 0.1), 0 8px 10px -6px rgba(15, 23, 42, 0.06)`.

## Shapes
Shapes align to `roundedness: 1` (Soft), creating a clean, disciplined, industrial look:
- Default components (buttons, input fields, badges, table cells): `0.25rem` (4px).
- Cards, containers, side panels: `rounded-lg` at `0.5rem` (8px).
- Dialogs, flyouts, and command palettes: `rounded-xl` at `0.75rem` (12px).
- Status indicators and live activity dots: Full circular pill (`9999px`).

## Components

### Buttons
- **Primary**: Solid `#2563EB` fill, white text, 4px radius, 36px height (`space-sm` vertical, `space-lg` horizontal padding), font weight 500. Hover state darkens to `#1D4ED8`. Active state scales subtly or darkens to `#1E40AF`.
- **Secondary / Outline**: `#FFFFFF` background, `#E2E8F0` border, `#0F172A` text. Hover shifts background to `#F1F5F9`.
- **Ghost**: Transparent background, `#64748B` text, shifts to `#F1F5F9` background and `#0F172A` text on hover.

### Input Fields & Search Bars
- Background `#FFFFFF`, 1px border `#E2E8F0`, 4px radius, 36px height, font size 14px.
- Placeholder text in `#94A3B8`.
- Focus state: Border transitions to `#2563EB` accompanied by a 2px outer ring with `rgba(37, 99, 235, 0.15)`.
- Shortcut indicators (e.g., `⌘K`) displayed right-aligned with `#F1F5F9` background and `#64748B` text.

### Chips & Filter Tags
- Height: 24px–28px, 4px radius, 12px label font size.
- Default: `#F8FAFC` background with a 1px `#E2E8F0` border and `#475569` text.
- Active: `#EFF6FF` background, `#2563EB` border, and `#1D4ED8` text with an optional inline dismiss icon.

### Job Cards & List Rows
- Crisp white background (`#FFFFFF`) with 1px `#E2E8F0` border and 8px border radius.
- Compact inner padding: `1rem` on mobile, `1.25rem` on desktop.
- Hover state transitions border to `#CBD5E1` and activates Level 2 shadow.
- Clear structural division: Company logo (36x36px rounded-md), role title in `#0F172A` semibold, metadata chips (salary, location, remote status) in muted `#64748B`, and a right-aligned quick-action button.

### Checkboxes & Radio Buttons
- 16x16px footprint with 4px border radius for checkboxes and circular geometry for radios.
- Unchecked: `#FFFFFF` fill with 1px `#CBD5E1` border.
- Checked: `#2563EB` solid fill with white checkmark icon or center dot. Focus ring matches inputs.

### Command Palette & Quick Filters
- Minimalist modal centered on the viewport with keyboard navigation support.
- Grouped category headers in 11px uppercase semibold (`#94A3B8`).
- Selected item highlighted with `#F1F5F9` background and `#2563EB` left accent marker.