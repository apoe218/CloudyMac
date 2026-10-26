# The H-Town Observer

A daily front page, rebuilt by `.github/workflows/pages.yml` and published live on GitHub Pages.

| Page | What it is |
|---|---|
| `/observer/index.html` | Full web edition (three columns on desktop, one on a phone) |
| `/observer/print.html` | One-page US-Letter print edition. Open it, press **Print this page**, and choose "Save as PDF" or your printer. Margins none, background graphics on. |

## Running it live from GitHub
- Automatic: rebuilds every morning (about 6:30am Houston) and on every push to the listed branches.
- On demand: repo **Actions** tab, **Deploy to GitHub Pages**, **Run workflow**. This pulls every source fresh.
- Settings, **Pages**, Source: **GitHub Actions**.

## Locally
`python3 observer/build.py` writes both files (standard library only, no installs).

## Tailoring
The `FEEDS` and team-ID block at the top of `build.py` controls every source, team and blocked keyword.
