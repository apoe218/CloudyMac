# The H-Town Observer

A daily front page, rebuilt by `.github/workflows/pages.yml` and published live on GitHub Pages.

| Page | What it is |
|---|---|
| `/observer/index.html` | Full web edition (three columns on desktop, one on a phone) |
| `/observer/print.html` | Three-page greyscale US-Letter print edition (page 1 front page, page 2 sports, page 3 a 15x15 crossword with yesterday's solution). Article text is pulled in so stories are readable. Press **Print this edition**, set margins to None. It shrinks type slightly and trims the lowest-priority stories automatically so each page fits. |

## Running it live from GitHub
- Automatic: rebuilds every morning (about 6:30am Houston). Scheduled runs only happen from the repo's **default branch**, so keep this code on the default branch (`main`). It also rebuilds on every push to the listed branches.
- On demand: repo **Actions** tab, **Deploy to GitHub Pages**, **Run workflow**. This pulls every source fresh.
- Settings, **Pages**, Source: **GitHub Actions**.

## Locally
`python3 observer/build.py` writes both files (standard library only, no installs).

## Tailoring
The `FEEDS` and team-ID block at the top of `build.py` controls every source, team and blocked keyword.

## Crossword
A general (not interest-themed) medium 15x15 puzzle on page 3 of the print edition. Words and dictionary-style clues come from the free Datamuse API (Wiktionary definitions), filtered to everyday-but-not-trivial words and saved in `observer/wordbank.json`. `observer/crossword.py` builds the grid, seeded by the date, so it changes daily and yesterday's solution can be regenerated. Refresh the word list any time with `python3 observer/refresh_wordbank.py`.
