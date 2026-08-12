# Fredspromenaden — The Peace Walk

A mobile-first PWA guide to [Ålands fredsinstitut's Peace Walk](https://peace.ax/mojligheter/fredspromenaden/) in Mariehamn: 11 stops through Åland's demilitarisation, autonomy, and peace-work history.

- Map + free-browse stop list, plus optional GPS proximity nudges ("you're near stop 4") — GPS never blocks manual navigation
- Full bilingual content (SV/EN), sourced verbatim from the institute's official PDF guides
- Installable (PWA manifest) and works offline once loaded (service worker caches map tiles + content)

## Coordinates need verification

Stop text is verbatim from the official guides. Coordinates are a mix:

- **Confirmed** (solid pin border): geocoded against a real, named address — stops 2, 4, 8, 10
- **Estimated** (dashed pin border): placed from the official route map + street context, not yet pinned to an exact building — stops 1, 3, 5, 6, 7, 9, 11

Each stop's `mapHint` field in [`src/data/stops.json`](src/data/stops.json) describes what to search for on Google Maps. Update `lat`/`lng` there and flip `confidence` to `"confirmed"` once checked.

## Development

```bash
npm install
npm run dev
```

Requires Node 20+ (the repo has a `dev.sh` wrapper that switches via nvm if your shell default is older).

## Build

```bash
npm run build
```
