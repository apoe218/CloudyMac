"""Daily crossword for the H-Town Observer print edition.

A 15x15 freeform puzzle generated from wordbank.json (everyday words with dictionary
definitions as clues, pulled from the free Datamuse/Wiktionary data), seeded by the date
so every morning is different and yesterday's solution can be regenerated exactly.
"""
import html
import json
import random
import re
from datetime import date
from pathlib import Path

SIZE = 15

def load_bank():
    """(answer, clue) pairs built by refresh_wordbank.py from free dictionary data."""
    rows = json.loads((Path(__file__).with_name("wordbank.json")).read_text(encoding="utf-8"))
    return [(a, clue) for a, clue, _freq in rows if 3 <= len(a) <= SIZE]


class Grid:
    def __init__(self):
        self.cells = {}   # (r,c) -> letter
        self.dirs = {}    # (r,c) -> set of 'A'/'D' words covering the cell
        self.words = []   # (answer, r, c, dir, clue)
        self.by_letter = {}  # letter -> [(r,c)]

    def fits(self, w, r, c, d):
        dr, dc = (0, 1) if d == "A" else (1, 0)
        n = len(w)
        er, ec = r + dr * n, c + dc * n
        if not (0 <= r < SIZE and 0 <= c < SIZE and 0 <= er - dr < SIZE and 0 <= ec - dc < SIZE):
            return -1
        if (r - dr, c - dc) in self.cells or (er, ec) in self.cells:
            return -1
        cross = 0
        for i, ch in enumerate(w):
            p = (r + dr * i, c + dc * i)
            have = self.cells.get(p)
            if have is not None:
                if have != ch or d in self.dirs[p]:
                    return -1
                cross += 1
            else:
                # empty cell: neighbours on either side (perpendicular) must be empty
                for q in ((p[0] + dc, p[1] + dr), (p[0] - dc, p[1] - dr)):
                    if q in self.cells:
                        return -1
        return cross

    def put(self, w, r, c, d, clue):
        dr, dc = (0, 1) if d == "A" else (1, 0)
        for i, ch in enumerate(w):
            p = (r + dr * i, c + dc * i)
            if p not in self.cells:
                self.by_letter.setdefault(ch, []).append(p)
            self.cells[p] = ch
            self.dirs.setdefault(p, set()).add(d)
        self.words.append((w, r, c, d, clue))

    def bbox(self):
        rs = [p[0] for p in self.cells]
        cs = [p[1] for p in self.cells]
        return min(rs), max(rs), min(cs), max(cs)


def attempt(bank, rng):
    g = Grid()
    # a random pool per attempt keeps this fast and makes every puzzle different
    order = rng.sample(bank, min(len(bank), 380))
    longs = [e for e in order if len(e[0]) >= 9] or order
    w, clue = rng.choice(longs)
    g.put(w, SIZE // 2 + rng.choice((-1, 0, 1)), (SIZE - len(w)) // 2, "A", clue)
    used = {w}
    while True:
        best, best_score = [], 0
        for w, clue in order:
            if w in used:
                continue
            for i, wc in enumerate(w):
                for pr, pc in g.by_letter.get(wc, ()):
                    for d in ("A", "D"):
                        r, c = (pr, pc - i) if d == "A" else (pr - i, pc)
                        k = g.fits(w, r, c, d)
                        if k < 1:
                            continue
                        score = k * 3 + len(w) * 0.3 + rng.random()
                        if score > best_score + 1e-9:
                            best, best_score = [(w, r, c, d, clue)], score
        if not best:
            break
        w, r, c, d, clue = best[0]
        g.put(w, r, c, d, clue)
        used.add(w)
    return g


def runs_ok(g):
    """Every run of 2+ letters in the grid must be exactly one placed answer."""
    found = set()
    for d in ("A", "D"):
        for r in range(SIZE):
            for c in range(SIZE):
                dr, dc = (0, 1) if d == "A" else (1, 0)
                if (r, c) in g.cells and (r - dr, c - dc) not in g.cells:
                    n = 0
                    while (r + dr * n, c + dc * n) in g.cells:
                        n += 1
                    if n >= 2:
                        found.add((r, c, d, n))
    placed = {(r, c, d, len(w)) for w, r, c, d, _ in g.words}
    return found == placed


def generate(day, tries=22):
    rng = random.Random(day.toordinal() * 7919)
    bank = load_bank()
    best, best_score = None, -1
    for _ in range(tries):
        g = attempt(bank, rng)
        if not runs_ok(g):
            continue
        r0, r1, c0, c1 = g.bbox()
        score = len(g.words) * 10 + (r1 - r0) + (c1 - c0) + len(g.cells) * 0.2
        if score > best_score:
            best, best_score = g, score
    return best


def number(g):
    """Standard numbering: reading order over cells that start a word."""
    starts = {}
    for w, r, c, d, clue in g.words:
        starts.setdefault((r, c), {})[d] = (w, clue)
    nums, n = {}, 0
    for r in range(SIZE):
        for c in range(SIZE):
            if (r, c) in starts:
                n += 1
                nums[(r, c)] = n
    across, down = [], []
    for (r, c), dd in starts.items():
        for d, (w, clue) in dd.items():
            (across if d == "A" else down).append((nums[(r, c)], clue, len(w)))
    return nums, sorted(across), sorted(down)


def render(day):
    """Return (puzzle_html, answers_html, stats) for a given date."""
    g = generate(day)
    y = generate(date.fromordinal(day.toordinal() - 1))
    nums, across, down = number(g)
    cells = []
    for r in range(SIZE):
        for c in range(SIZE):
            if (r, c) in g.cells:
                n = nums.get((r, c))
                cells.append(f'<div>{f"<i>{n}</i>" if n else ""}</div>')
            else:
                cells.append('<div class="b"></div>')

    def clue_list(items):
        return "".join(f'<li value="{n}"><b>{n}</b> {html.escape(clue)} <span>({ln})</span></li>'
                       for n, clue, ln in items)

    ymini = []
    for r in range(SIZE):
        for c in range(SIZE):
            ch = y.cells.get((r, c))
            ymini.append(f'<div>{ch}</div>' if ch else '<div class="b"></div>')
    puzzle = (f'<div class="xw">{"".join(cells)}</div>'
              f'<div class="clues"><div><h4>Across</h4><ol>{clue_list(across)}</ol></div>'
              f'<div><h4>Down</h4><ol>{clue_list(down)}</ol></div></div>')
    answers = f'<div class="xwmini">{"".join(ymini)}</div>'
    return puzzle, answers, {"words": len(g.words), "across": len(across), "down": len(down)}


if __name__ == "__main__":
    import sys, time
    t = time.time()
    day = date.today()
    g = generate(day)
    for r in range(SIZE):
        print("".join(g.cells.get((r, c), "·") for c in range(SIZE)))
    print(len(g.words), "words", round(time.time() - t, 1), "s", file=sys.stderr)
