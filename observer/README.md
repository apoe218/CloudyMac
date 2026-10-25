# The H-Town Observer

A daily front page, rebuilt every morning by `.github/workflows/pages.yml` and
published at `/observer/` on the site.

- Weather: Space City Weather (latest post), NWS 7-day + alerts, NHC tropics
- Aggies/SEC: ESPN schedule, AP rank, SEC standings, Texas A&M and SEC headlines
- Liverpool: fixtures, Premier League and Champions League tables, headlines
- Houston, national and world headlines

Run locally: `python3 observer/build.py && open observer/index.html`

Tailor it by editing the `FEEDS` and team-ID block at the top of `build.py`.
