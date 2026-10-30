import { shuffledDeck, isRed } from '../core/deck.js';

// redeals: -1 = unlimited. scoring: 'standard' | 'vegas' | 'none'.
export const DEFAULTS = { draw: 3, scoring: 'standard', redeals: -1 };

export const FOUNDATIONS = ['f0', 'f1', 'f2', 'f3'];
export const TABLEAU = ['t0', 't1', 't2', 't3', 't4', 't5', 't6'];

export function newGame(seed, options = {}) {
  const opts = { ...DEFAULTS, ...options };
  const deck = shuffledDeck(seed);
  const tableau = [];
  for (let i = 0; i < 7; i++) {
    const col = deck.splice(0, i + 1);
    col[i].up = true;
    tableau.push(col);
  }
  return {
    seed,
    opts,
    stock: deck,
    waste: [],
    fan: 0, // how many waste cards are shown fanned out (draw-3)
    foundations: [[], [], [], []],
    tableau,
    score: opts.scoring === 'vegas' ? -52 : 0,
    moves: 0,
    redealsUsed: 0,
  };
}

export function getPile(s, id) {
  if (id === 'stock') return s.stock;
  if (id === 'waste') return s.waste;
  return id[0] === 'f' ? s.foundations[+id[1]] : s.tableau[+id[1]];
}

// Can the run starting at `idx` in `from` be picked up at all?
export function movableRun(s, from, idx) {
  if (from === 'stock') return false;
  const src = getPile(s, from);
  if (idx < 0 || idx >= src.length) return false;
  if (from === 'waste' || from[0] === 'f') return idx === src.length - 1;
  return src.slice(idx).every((c) => c.up);
}

export function canMove(s, from, idx, to) {
  if (from === to || !movableRun(s, from, idx)) return false;
  const cards = getPile(s, from).slice(idx);
  const head = cards[0];
  const dest = getPile(s, to);
  const top = dest[dest.length - 1];
  if (to[0] === 'f') {
    if (from[0] === 'f' || cards.length !== 1) return false;
    return top ? top.s === head.s && head.r === top.r + 1 : head.r === 1;
  }
  if (to[0] === 't') {
    if (!top) return head.r === 13;
    return top.up && isRed(top.s) !== isRed(head.s) && head.r === top.r - 1;
  }
  return false;
}

// Mutates `s`. Returns false (and changes nothing) if the move is illegal.
export function move(s, from, idx, to) {
  if (!canMove(s, from, idx, to)) return false;
  const src = getPile(s, from);
  getPile(s, to).push(...src.splice(idx));
  const { scoring } = s.opts;
  let delta = 0;
  if (scoring === 'vegas') {
    if (to[0] === 'f') delta += 5;
    if (from[0] === 'f') delta -= 5;
  } else if (scoring === 'standard') {
    if (to[0] === 'f') delta += 10;
    else if (from === 'waste') delta += 5;
    else if (from[0] === 'f') delta -= 15;
  }
  if (from[0] === 't' && src.length && !src[src.length - 1].up) {
    src[src.length - 1].up = true;
    if (scoring === 'standard') delta += 5;
  }
  if (from === 'waste') s.fan = Math.max(1, s.fan - 1);
  s.score += delta;
  s.moves++;
  return true;
}

export function canDraw(s) {
  if (s.stock.length) return true;
  if (!s.waste.length) return false;
  return s.opts.redeals < 0 || s.redealsUsed < s.opts.redeals;
}

// Turn over from the stock, or recycle the waste when the stock is empty.
export function draw(s) {
  if (!canDraw(s)) return false;
  if (s.stock.length) {
    const n = Math.min(s.opts.draw, s.stock.length);
    for (let i = 0; i < n; i++) {
      const c = s.stock.pop();
      c.up = true;
      s.waste.push(c);
    }
    s.fan = n;
  } else {
    while (s.waste.length) {
      const c = s.waste.pop();
      c.up = false;
      s.stock.push(c);
    }
    s.redealsUsed++;
    s.fan = 0;
    if (s.opts.scoring === 'standard') {
      s.score = Math.max(0, s.score - (s.opts.draw === 1 ? 100 : 20));
    }
  }
  s.moves++;
  return true;
}

// Where a tapped card should go: foundation first, then a built tableau pile, then an empty one.
export function autoDest(s, from, idx) {
  if (idx === getPile(s, from).length - 1) {
    for (const f of FOUNDATIONS) if (canMove(s, from, idx, f)) return f;
  }
  const fits = TABLEAU.filter((t) => canMove(s, from, idx, t));
  const built = fits.find((t) => getPile(s, t).length);
  if (built) return built;
  // Moving a king that's already at the bottom of its column to an empty one is pointless.
  const empty = fits.find((t) => !(from[0] === 't' && idx === 0));
  return empty ?? null;
}

// All useful moves, best first. Weight: 4 reveals a hidden card, 3 to foundation,
// 2 from waste, 1 other, 0.5 shuffles a run between built columns.
export function findMoves(s) {
  const out = [];
  const sources = [];
  if (s.waste.length) sources.push(['waste', s.waste.length - 1]);
  s.tableau.forEach((col, i) => col.forEach((c, j) => c.up && sources.push(['t' + i, j])));
  for (const [from, idx] of sources) {
    for (const to of [...FOUNDATIONS, ...TABLEAU]) {
      if (!canMove(s, from, idx, to)) continue;
      const src = getPile(s, from);
      const emptyDest = !getPile(s, to).length;
      if (to[0] === 't' && emptyDest && from[0] === 't' && idx === 0) continue;
      let w = 1;
      if (from[0] === 't' && idx > 0 && !src[idx - 1].up) w = 4;
      else if (to[0] === 'f') w = 3;
      else if (from === 'waste') w = 2;
      else if (from[0] === 't' && idx > 0) w = 0.5;
      out.push({ from, idx, to, w });
    }
  }
  return out.sort((a, b) => b.w - a.w);
}

export const isWon = (s) => s.foundations.every((f) => f.length === 13);

export const canAutoComplete = (s) =>
  !isWon(s) && !s.stock.length && !s.waste.length && s.tableau.every((c) => c.every((x) => x.up));

// One step of auto-complete: send any available card to a foundation.
export function autoStep(s) {
  for (const t of TABLEAU) {
    const col = getPile(s, t);
    if (!col.length) continue;
    for (const f of FOUNDATIONS) if (move(s, t, col.length - 1, f)) return true;
  }
  return false;
}
