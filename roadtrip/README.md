# Road Trip Planner (proof of concept)

A single-file, no-build web/mobile map app for planning a road trip. No API keys.

Serve it over http (not by double-clicking the file, which sends no Referer and gets blocked by Nominatim). Use any static server (e.g. `python3 -m http.server` inside this folder), then open `http://localhost:8000`.

## What it does
- Add stops by searching a place or clicking the map; drag the list to reorder, drag pins to move.
- Routes through all stops (OSRM) and shows per-leg miles, time, gallons and fuel cost.
- Vehicle picker pulls EPA mpg from fueleconomy.gov (or type your own mpg, tank size and $/gal).
- Fuel-stop planner: finds gas stations along the route (OpenStreetMap via Overpass) and picks stops
  so you never drop below your refuel threshold; warns if a stretch has no stations.
- Overnight splits based on a max-driving-hours-per-day budget.
- Hand-off: "Open in Google Maps" for turn-by-turn, or copy the trip as JSON.

## Free services used (keyless, light personal use only)
| Need | Service |
|---|---|
| Map | MapLibre GL + OpenFreeMap vector tiles (OSM data; the openstreetmap.org tile servers forbid app use) |
| Routing | OSRM public demo server |
| Geocoding | Nominatim |
| Gas stations | Overpass API (OSM) |
| MPG | fueleconomy.gov |

## Known limits
- OSM has no live gas prices; you enter a $/gal figure.
- No elevation/weather yet, so mpg is flat.
- Public demo servers rate-limit; heavy use needs self-hosting or paid APIs.
- Planned next: Google Places "search along route" and fuel prices, attractions/lodging layers.
