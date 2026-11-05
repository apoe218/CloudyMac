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
| Routing | Valhalla (FOSSGIS), falling back to OSRM demo and OSRM (FOSSGIS) |
| Geocoding | Nominatim |
| Gas stations | Overpass API (OSM) |
| MPG | fueleconomy.gov |

## Google Places layer (optional, your own key)
After you plan a trip, the **Places along route** panel uses Google Places API (New) text search with
`searchAlongRouteParameters`, so results are biased to places with the smallest detour.
- Gas, food, coffee, lodging, sights, camping, EV charging, plus a custom search. Ratings and gas prices
  (where Google has them) show in the list; "Use average regular price" fills the $/gal box.
- "+ Stop" inserts a place into the trip at the right position; press Plan trip again to re-route.
- The route is searched in sections (default every 300 mi, max 20 results each); the panel shows how many
  requests a search will make before you run it.

Key setup (Google Cloud console): create a project, enable billing, enable **Places API (New)**, create an API key,
and restrict it: Application restrictions -> Websites (e.g. `http://localhost:8000/*`), API restrictions -> Places API (New).
Also set a budget alert and a daily quota. Paste the key into the panel; it is stored only in your browser's localStorage.
Ratings and fuel prices use a higher-priced field tier than basic place data; uncheck the box to cut cost.

## Known limits
- OpenStreetMap has no live gas prices; enter a $/gal figure, or use Google's prices via the Places layer.
- No elevation/weather yet, so mpg is flat.
- Public demo servers rate-limit; heavy use needs self-hosting or paid APIs.
- Public Valhalla caps one request at ~1,500 km, so it is called one leg at a time; legs longer than that fall back to OSRM.
- The Overpass fuel-stop planner still uses OpenStreetMap stations, not Google's results.
