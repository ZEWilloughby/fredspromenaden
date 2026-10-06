# Fredspromenaden — The Peace Walk

A mobile-first PWA guide to [Ålands fredsinstitut's Peace Walk](https://peace.ax/mojligheter/fredspromenaden/) in Mariehamn: 11 stops through Åland's demilitarisation, autonomy, and peace-work history.

- Map + free-browse stop list, plus optional GPS proximity nudges ("you're near stop 4"); GPS never blocks manual navigation
- Remembers the chosen language and which stops have been read
- Full bilingual content (SV/EN), sourced verbatim from the institute's official PDF guides
- Installable (PWA manifest) and works offline once loaded (service worker caches map tiles + content)

## Links to stops

Each stop has its own address, e.g. `…/#/stopp/4`, which opens that stop directly (useful for QR codes on site). The phone's back button returns to the map.

## Coordinates

Stop text is verbatim from the official guides. All 11 coordinates have been confirmed, either on site or against a named address. The source for each is recorded in [`notes/coordinates.json`](notes/coordinates.json), which is kept out of the app bundle.

To move a stop, edit `lat`/`lng` in [`src/data/stops.json`](src/data/stops.json) and update its note. A stop added later with an unchecked position can be marked `"confidence": "estimated"`, which gives its pin a dashed border.

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

The build uses relative paths, so `dist/` can be served from a domain root or a subpath. CI runs lint and build on every push.
