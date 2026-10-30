import { SUITS, RANKS, RANK_NAMES, SUIT_NAMES, isRed } from '../core/deck.js';
import {
  newGame, move, draw, canDraw, canMove, movableRun, autoDest, findMoves, getPile,
  isWon, canAutoComplete, autoStep, DEFAULTS, FOUNDATIONS, TABLEAU,
} from '../games/klondike.js';

const SAVE_KEY = 'klondike.save';
const SETTINGS_KEY = 'klondike.settings';
const STATS_KEY = 'klondike.stats';

const UP_STEP = 0.3; // vertical offset between face-up cards, in card heights
const DOWN_STEP = 0.12; // ...and between face-down cards

const $ = (id) => document.getElementById(id);
const store = {
  get(key, fallback) {
    try { return JSON.parse(localStorage.getItem(key)) ?? fallback; } catch { return fallback; }
  },
  set(key, value) {
    try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* storage unavailable */ }
  },
};

let settings = { ...DEFAULTS, table: 'green', back: 'blue', ...store.get(SETTINGS_KEY, {}) };
let state;
let history = [];
let time = 0;
let running = false;
let counted = false; // has this deal been counted as "played" yet
let busy = false; // blocks input during auto-complete
let daily = false;

const pileEls = {};

// ---------- setup ----------

function buildBoard() {
  const make = (id, label, parent, extra = '') => {
    const el = document.createElement('div');
    el.className = 'pile ' + extra;
    el.dataset.id = id;
    if (label) el.dataset.label = label;
    parent.append(el);
    pileEls[id] = el;
  };
  const top = $('top');
  make('stock', '', top);
  make('waste', '', top);
  const spacer = document.createElement('div');
  spacer.className = 'pile spacer';
  top.append(spacer);
  FOUNDATIONS.forEach((id) => make(id, 'A', top));
  TABLEAU.forEach((id) => make(id, '', $('tableau')));
  pileEls.stock.id = 'stock';
  pileEls.stock.addEventListener('click', () => {
    if (!busy) act((s) => draw(s));
  });
}

function applyAppearance() {
  document.body.dataset.table = settings.table;
  document.body.dataset.back = settings.back;
}

function seedFromToday() {
  const d = new Date();
  return d.getFullYear() * 10000 + (d.getMonth() + 1) * 100 + d.getDate();
}

function startGame({ seed, isDaily = false } = {}) {
  daily = isDaily;
  const opts = { draw: settings.draw, scoring: settings.scoring, redeals: settings.redeals };
  state = newGame(seed ?? Math.floor(Math.random() * 2 ** 32), opts);
  history = [];
  time = 0;
  running = false;
  counted = false;
  busy = false;
  render();
  save();
}

// ---------- rendering ----------

function cardEl(c, pile, idx) {
  const el = document.createElement('div');
  el.className = `card ${c.up ? 'up' : 'down'} ${isRed(c.s) ? 'red' : 'black'}`;
  el.dataset.pile = pile;
  el.dataset.idx = idx;
  if (c.up) {
    const corner = document.createElement('span');
    corner.className = 'corner';
    corner.append(RANKS[c.r], document.createElement('br'), SUITS[c.s]);
    const pip = document.createElement('span');
    pip.className = 'pip';
    pip.textContent = c.r > 10 ? RANKS[c.r] : SUITS[c.s];
    el.append(corner, pip);
    el.setAttribute('aria-label', `${RANK_NAMES[c.r]} of ${SUIT_NAMES[c.s]}`);
  } else {
    el.setAttribute('aria-label', 'Face-down card');
  }
  return el;
}

function render() {
  const s = state;

  const stock = pileEls.stock;
  stock.replaceChildren();
  stock.classList.toggle('empty', !s.stock.length);
  stock.dataset.label = canDraw(s) ? '↺' : '✕';
  if (s.stock.length) stock.append(cardEl(s.stock[s.stock.length - 1], 'stock', s.stock.length - 1));

  const waste = pileEls.waste;
  waste.replaceChildren();
  waste.style.overflow = 'visible';
  const shown = Math.min(Math.max(s.fan, s.waste.length ? 1 : 0), s.waste.length);
  for (let i = s.waste.length - shown; i < s.waste.length; i++) {
    const el = cardEl(s.waste[i], 'waste', i);
    el.style.left = `calc(var(--cw) * 0.24 * ${i - (s.waste.length - shown)})`;
    waste.append(el);
  }

  s.foundations.forEach((f, i) => {
    const el = pileEls['f' + i];
    el.replaceChildren();
    el.classList.toggle('empty', !f.length);
    if (f.length) el.append(cardEl(f[f.length - 1], 'f' + i, f.length - 1));
  });

  s.tableau.forEach((col, i) => {
    const el = pileEls['t' + i];
    el.replaceChildren();
    el.classList.toggle('empty', !col.length);
    let k = 0;
    col.forEach((c, j) => {
      const card = cardEl(c, 't' + i, j);
      card.style.top = `calc(var(--ch) * ${k})`;
      el.append(card);
      if (j < col.length - 1) k += c.up ? UP_STEP : DOWN_STEP;
    });
    el.style.height = `calc(var(--ch) * ${1 + k})`;
  });

  $('score').textContent = s.opts.scoring === 'none' ? '–' : s.score;
  $('moves').textContent = s.moves;
  $('time').textContent = fmtTime(time);
  $('btn-undo').disabled = !history.length || busy;
}

const fmtTime = (t) => `${Math.floor(t / 60)}:${String(t % 60).padStart(2, '0')}`;

function toast(msg) {
  const el = $('toast');
  el.textContent = msg;
  el.classList.add('show');
  clearTimeout(toast.t);
  toast.t = setTimeout(() => el.classList.remove('show'), 1600);
}

// ---------- actions ----------

function act(fn) {
  if (busy) return false;
  const snap = structuredClone(state);
  if (!fn(state)) return false;
  history.push(snap);
  if (history.length > 300) history.shift();
  running = true;
  if (!counted) {
    counted = true;
    if (!daily) bumpStats((st) => { st.played++; });
  }
  render();
  save();
  afterAction();
  return true;
}

function afterAction() {
  if (isWon(state)) return win();
  if (canAutoComplete(state)) autoComplete();
}

function autoComplete() {
  busy = true;
  const tick = () => {
    const snap = structuredClone(state);
    if (autoStep(state)) {
      history.push(snap);
      render();
      if (isWon(state)) { busy = false; return win(); }
      setTimeout(tick, 70);
    } else {
      busy = false;
      render();
    }
  };
  tick();
}

function undo() {
  if (busy || !history.length) return;
  state = history.pop();
  render();
  save();
}

function hint() {
  if (busy) return;
  document.querySelectorAll('.hint').forEach((e) => e.classList.remove('hint'));
  const moves = findMoves(state);
  const best = moves[0];
  let els;
  if (best && best.w >= 2) {
    els = [...pileEls[best.from].querySelectorAll('.card')].filter((e) => +e.dataset.idx >= best.idx);
  } else if (canDraw(state)) {
    els = [pileEls.stock];
    toast(state.stock.length ? 'Draw from the stock' : 'Recycle the waste');
  } else if (best) {
    els = [...pileEls[best.from].querySelectorAll('.card')].filter((e) => +e.dataset.idx >= best.idx);
  } else {
    return toast('No moves left — try Undo or a new deal');
  }
  els.forEach((e) => e.classList.add('hint'));
  if (best && els[0] !== pileEls.stock) pileEls[best.to].classList.add('drop');
  setTimeout(() => {
    document.querySelectorAll('.hint').forEach((e) => e.classList.remove('hint'));
    document.querySelectorAll('.drop').forEach((e) => e.classList.remove('drop'));
  }, 1400);
}

// ---------- input: tap to auto-move, drag to place ----------

let drag = null;

$('board').addEventListener('pointerdown', (e) => {
  if (busy || e.button > 0) return;
  const el = e.target.closest('.card.up');
  if (!el) return;
  const pile = el.dataset.pile;
  const idx = +el.dataset.idx;
  if (!movableRun(state, pile, idx)) return;
  drag = { pile, idx, el, x: e.clientX, y: e.clientY, active: false, id: e.pointerId };
});

window.addEventListener('pointermove', (e) => {
  if (!drag || e.pointerId !== drag.id) return;
  if (!drag.active) {
    if (Math.hypot(e.clientX - drag.x, e.clientY - drag.y) < 6) return;
    startDrag();
  }
  const layer = $('drag-layer');
  layer.style.transform = `translate(${e.clientX - drag.dx}px, ${e.clientY - drag.dy}px)`;
  highlightDrop(dropTarget(drag, e.clientX, e.clientY));
});

window.addEventListener('pointerup', (e) => {
  if (!drag || e.pointerId !== drag.id) return;
  const d = drag;
  drag = null;
  clearDrag();
  if (!d.active) {
    const dest = autoDest(state, d.pile, d.idx);
    if (dest) act((s) => move(s, d.pile, d.idx, dest));
    return;
  }
  const dest = dropTarget(d, e.clientX, e.clientY);
  if (!(dest && act((s) => move(s, d.pile, d.idx, dest)))) render();
});

window.addEventListener('pointercancel', () => {
  if (!drag) return;
  drag = null;
  clearDrag();
  render();
});

function startDrag() {
  const run = [...pileEls[drag.pile].querySelectorAll('.card')].filter((e) => +e.dataset.idx >= drag.idx);
  const first = run[0].getBoundingClientRect();
  drag.dx = drag.x - first.left;
  drag.dy = drag.y - first.top;
  const layer = $('drag-layer');
  layer.replaceChildren();
  for (const el of run) {
    const r = el.getBoundingClientRect();
    const clone = el.cloneNode(true);
    clone.style.cssText = `top:${r.top - first.top}px;left:${r.left - first.left}px;width:${r.width}px;height:${r.height}px;`;
    layer.append(clone);
    el.classList.add('hidden');
  }
  drag.active = true;
}

function clearDrag() {
  $('drag-layer').replaceChildren();
  document.querySelectorAll('.card.hidden').forEach((e) => e.classList.remove('hidden'));
  highlightDrop(null);
}

// The pointer's pile if the move is legal there, else the pile under the dragged card's centre.
function dropTarget(d, x, y) {
  const probe = (px, py) => document.elementFromPoint(px, py)?.closest('.pile')?.dataset.id;
  const cw = pileEls.t0.getBoundingClientRect().width;
  const spots = [[x, y], [x - d.dx + cw / 2, y - d.dy + cw * 0.7]];
  for (const [px, py] of spots) {
    const id = probe(px, py);
    if (id && canMove(state, d.pile, d.idx, id)) return id;
  }
  return null;
}

function highlightDrop(id) {
  for (const [pid, el] of Object.entries(pileEls)) el.classList.toggle('drop', pid === id);
}

// ---------- stats / save ----------

function bumpStats(fn) {
  const all = store.get(STATS_KEY, {});
  const key = `draw${state.opts.draw}-${state.opts.scoring}`;
  const st = all[key] ?? { played: 0, won: 0, streak: 0, bestStreak: 0, bestTime: null, bestScore: null };
  fn(st);
  all[key] = st;
  store.set(STATS_KEY, all);
  return st;
}

function win() {
  running = false;
  let st = null;
  if (!daily) {
    st = bumpStats((x) => {
      x.won++;
      x.streak++;
      x.bestStreak = Math.max(x.bestStreak, x.streak);
      x.bestTime = x.bestTime === null ? time : Math.min(x.bestTime, time);
      if (state.opts.scoring !== 'none') x.bestScore = Math.max(x.bestScore ?? -Infinity, state.score);
    });
  }
  localStorage.removeItem(SAVE_KEY);
  const body = $('win-body');
  body.replaceChildren();
  const lines = [`Time ${fmtTime(time)} · ${state.moves} moves`];
  if (state.opts.scoring !== 'none') lines.push(`Score ${state.score}`);
  if (st) lines.push(`Win streak ${st.streak} · Best time ${fmtTime(st.bestTime)}`);
  for (const l of lines) {
    const p = document.createElement('p');
    p.textContent = l;
    body.append(p);
  }
  $('win').showModal();
}

function showStats() {
  const all = store.get(STATS_KEY, {});
  const body = $('stats-body');
  body.replaceChildren();
  const keys = Object.keys(all);
  if (!keys.length) {
    body.textContent = 'No games played yet.';
  } else {
    const table = document.createElement('table');
    const head = table.insertRow();
    for (const h of ['Mode', 'Played', 'Won', 'Best streak', 'Best time']) {
      const th = document.createElement('th');
      th.textContent = h;
      head.append(th);
    }
    for (const k of keys) {
      const st = all[k];
      const [d, sc] = k.split('-');
      const row = table.insertRow();
      const cells = [
        `Draw ${d.slice(4)} · ${sc}`, st.played, st.won, st.bestStreak, st.bestTime === null ? '–' : fmtTime(st.bestTime),
      ];
      for (const c of cells) row.insertCell().textContent = c;
    }
    body.append(table);
  }
  $('stats').showModal();
}

function save() {
  if (isWon(state)) return;
  store.set(SAVE_KEY, { state, time, counted, daily });
}

function restore() {
  const saved = store.get(SAVE_KEY, null);
  if (!saved?.state) return false;
  state = saved.state;
  time = saved.time ?? 0;
  counted = !!saved.counted;
  daily = !!saved.daily;
  history = [];
  running = state.moves > 0;
  render();
  if (canAutoComplete(state)) autoComplete();
  return true;
}

// ---------- settings dialog & buttons ----------

function openSettings() {
  const f = $('settings-form');
  f.elements.draw.value = String(settings.draw);
  f.elements.scoring.value = settings.scoring;
  f.elements.redeals.value = String(settings.redeals);
  f.elements.table.value = settings.table;
  f.elements.back.value = settings.back;
  $('settings').showModal();
}

$('settings').addEventListener('close', () => {
  if ($('settings').returnValue !== 'ok') return;
  const f = $('settings-form').elements;
  const next = {
    ...settings,
    draw: +f.draw.value,
    scoring: f.scoring.value,
    redeals: +f.redeals.value,
    table: f.table.value,
    back: f.back.value,
  };
  const rulesChanged = ['draw', 'scoring', 'redeals'].some((k) => next[k] !== settings[k]);
  if (rulesChanged && state.moves > 0 && !confirm('Changing the rules starts a new deal. Continue?')) return;
  settings = next;
  store.set(SETTINGS_KEY, settings);
  applyAppearance();
  if (rulesChanged) startGame();
});

function confirmNew(fn) {
  if (!state.moves || isWon(state) || confirm('Abandon this game and start a new one?')) {
    if (state.moves && !isWon(state) && counted && !daily) bumpStats((st) => { st.streak = 0; });
    fn();
  }
}

$('btn-new').addEventListener('click', () => confirmNew(() => startGame()));
$('btn-daily').addEventListener('click', () => confirmNew(() => { startGame({ seed: seedFromToday(), isDaily: true }); toast('Daily deal — same cards for everyone today'); }));
$('btn-undo').addEventListener('click', undo);
$('btn-hint').addEventListener('click', hint);
$('btn-stats').addEventListener('click', showStats);
$('btn-settings').addEventListener('click', openSettings);
$('stats-reset').addEventListener('click', () => {
  if (confirm('Reset all statistics?')) { store.set(STATS_KEY, {}); showStats(); }
});
$('win-new').addEventListener('click', () => startGame());
window.addEventListener('keydown', (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key === 'z') { e.preventDefault(); undo(); }
});

setInterval(() => {
  if (running && !busy && !document.hidden) {
    time++;
    $('time').textContent = fmtTime(time);
  }
}, 1000);

// ---------- boot ----------

buildBoard();
applyAppearance();
if (!restore()) startGame();
