# Vendored assets

Served by the application from `/static` (ADR-0021, constitution II). Nothing here is
fetched at runtime. Update a file only together with its row below.

| File | Source | Version | Licence | SHA-256 |
|---|---|---|---|---|
| `vendor/htmx-2.0.3.min.js` | https://unpkg.com/htmx.org@2.0.3/dist/htmx.min.js | 2.0.3 | 0BSD | `491955cd1810747d7d7b9ccb936400afb760e06d25d53e4572b64b6563b2784e` |
| `fonts/inter-latin-wght-normal.woff2` | https://cdn.jsdelivr.net/npm/@fontsource-variable/inter@5.3.0/files/inter-latin-wght-normal.woff2 | 5.3.0 | OFL-1.1 | `3100e775e8616cd2611beecfa23a4263d7037586789b43f035236a2e6fbd4c62` |
| `fonts/inter-latin-ext-wght-normal.woff2` | https://cdn.jsdelivr.net/npm/@fontsource-variable/inter@5.3.0/files/inter-latin-ext-wght-normal.woff2 | 5.3.0 | OFL-1.1 | `34b9c504cab7a73e37b746343a449132e56cf7b5481af2cb81dc74dcff25c956` |
| `icons.svg` | `@material-symbols/svg-400@0.48.3/outlined/*.svg`, combined into one `<symbol>` sprite | 0.48.3 | Apache-2.0 | `61192093c99babac345d345043123a7d926c303ee159cb9561750e578e02b60a` |

htmx 2.0.3 SHA-384 (for `integrity=`):
`sha384-0895/pl2MU10Hqc6jd4RvrthNlDiE9U1tWmX7WRESftEDRosgxNsQG/Ze9YMRzHq`

## Icon sprite

Glyphs (21): `fiber_new`, `check_circle`, `send`, `cancel`, `block`, `undo`, `play_arrow`,
`delete`, `search`, `expand_more`, `arrow_forward`, `open_in_new`, `settings`, `info`,
`warning`, `error`, `schedule`, `lock`, `check`, `progress_activity`, `location_on`.

Each symbol keeps its `viewBox`, has no `fill`, and its `id` is the glyph name.

**Deviation:** `expand_more` does not exist in `@material-symbols/svg-400@0.48.3`. The sprite
symbol `expand_more` is built from that package's `keyboard_arrow_down` (the same chevron),
so templates can still use the id `expand_more`.

## Notices

- **Inter** is copyright the Inter Project Authors (https://github.com/rsms/inter), licensed
  under the SIL Open Font License 1.1 (https://openfontlicense.org). The font files are
  unmodified.
- **Material Symbols** are copyright Google LLC, licensed under the Apache License 2.0
  (https://www.apache.org/licenses/LICENSE-2.0).
- **htmx** is copyright Big Sky Software, licensed under the Zero-Clause BSD licence.
