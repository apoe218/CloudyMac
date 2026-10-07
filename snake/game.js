'use strict';

/* =====================================================================
   1. CONFIG: the main knobs to tweak
   ===================================================================== */
const CONFIG = {
  gridSize: 20,            // cells per side (board is always square)
  startLength: 3,          // initial snake segments
  pointsFood: 10,
  pointsGolden: 50,

  foodsPerLevel: 5,        // speed goes up every N foods eaten
  speedStepMs: 6,          // how much each level shortens the tick interval
  minTickMs: 50,           // fastest allowed speed (lower = faster)

  // tickMs = starting time between snake moves (lower = faster)
  difficulties: {
    easy:   { label: 'Easy',   tickMs: 150, wrap: true,  hint: 'Slower start. The snake wraps around walls.' },
    normal: { label: 'Normal', tickMs: 110, wrap: false, hint: 'Balanced speed. Walls are deadly.' },
    hard:   { label: 'Hard',   tickMs: 75,  wrap: false, hint: 'Fast from the start. Walls are deadly.' },
  },
  defaultDifficulty: 'normal',

  golden: {
    chance: 0.15,          // chance a golden apple appears after eating regular food
    lifetimeMs: 5000,      // how long it stays (game time, so pausing freezes it)
    blinkMs: 1500,         // starts blinking when this much time is left
  },

  maxQueuedInputs: 3,      // buffered direction presses
  swipeMinPx: 24,          // swipe distance needed on touch screens
  gameOverShakeMs: 450,
  gameOverOverlayDelayMs: 600,
  maxFrameMs: 100,         // clamp huge frame gaps (e.g. returning to a background tab)

  colors: {
    bg: '#0b0f1a',
    grid: 'rgba(255, 255, 255, 0.045)',
    snakeHead: '#4ade80',
    snakeTail: '#0891b2',
    food: '#fb7185',
    golden: '#fbbf24',
    goldenLight: '#fff3b0',
  },
};

const DIRS = {
  up:    { x: 0,  y: -1 },
  down:  { x: 0,  y: 1 },
  left:  { x: -1, y: 0 },
  right: { x: 1,  y: 0 },
};

/* =====================================================================
   2. Utilities
   ===================================================================== */
const $ = (id) => document.getElementById(id);

// localStorage can throw (private mode, blocked storage), so always wrap it.
function storeGet(key, fallback) {
  try { const v = localStorage.getItem(key); return v === null ? fallback : v; }
  catch (e) { return fallback; }
}
function storeSet(key, value) {
  try { localStorage.setItem(key, String(value)); } catch (e) { /* ignore */ }
}

function hexToRgb(hex) {
  const n = parseInt(hex.slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}
const HEAD_RGB = hexToRgb(CONFIG.colors.snakeHead);
const TAIL_RGB = hexToRgb(CONFIG.colors.snakeTail);
function mixColor(a, b, t) {
  return `rgb(${Math.round(a[0] + (b[0] - a[0]) * t)}, ${Math.round(a[1] + (b[1] - a[1]) * t)}, ${Math.round(a[2] + (b[2] - a[2]) * t)})`;
}

function roundedRect(ctx, x, y, w, h, r) {
  r = Math.min(r, w / 2, h / 2);
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}

/* =====================================================================
   3. Game state
   screen: 'start' | 'playing' | 'paused' | 'over'
   ===================================================================== */
const G = CONFIG.gridSize;

const state = {
  screen: 'start',
  difficulty: CONFIG.defaultDifficulty,
  snake: [],          // [{x, y}], head first
  dir: DIRS.right,    // direction of the last completed move
  queue: [],          // buffered direction changes
  food: null,         // {x, y}
  golden: null,       // {x, y, left} (left = ms remaining)
  score: 0,
  best: 0,
  bestAtStart: 0,
  newRecord: false,
  eaten: 0,
  tickMs: 110,
  acc: 0,             // accumulated time toward the next tick
  particles: [],
  shake: 0,           // ms of screen shake remaining
  overAt: 0,
  overShown: false,
  won: false,
};

function level() { return 1 + Math.floor(state.eaten / CONFIG.foodsPerLevel); }

function tickInterval() {
  const base = CONFIG.difficulties[state.difficulty].tickMs;
  return Math.max(CONFIG.minTickMs, base - (level() - 1) * CONFIG.speedStepMs);
}

function bestKey() { return 'snake.best.' + state.difficulty; }

function resetGame() {
  const mid = Math.floor(G / 2);
  state.snake = [];
  for (let i = 0; i < CONFIG.startLength; i++) state.snake.push({ x: mid - i, y: mid });
  state.dir = DIRS.right;
  state.queue = [];
  state.golden = null;
  state.particles = [];
  state.score = 0;
  state.eaten = 0;
  state.acc = 0;
  state.shake = 0;
  state.newRecord = false;
  state.won = false;
  state.overShown = false;
  state.best = parseInt(storeGet(bestKey(), '0'), 10) || 0;
  state.bestAtStart = state.best;
  state.tickMs = tickInterval();
  state.food = null;
  state.food = randomEmptyCell();
  updateHud();
}

/* =====================================================================
   4. Collision & spawning logic
   ===================================================================== */
function sameCell(a, b) { return !!a && !!b && a.x === b.x && a.y === b.y; }

// Pick a random cell that is not occupied by the snake, food or golden apple.
function randomEmptyCell() {
  const taken = new Set(state.snake.map((s) => s.y * G + s.x));
  if (state.food) taken.add(state.food.y * G + state.food.x);
  if (state.golden) taken.add(state.golden.y * G + state.golden.x);
  const free = [];
  for (let i = 0; i < G * G; i++) if (!taken.has(i)) free.push(i);
  if (!free.length) return null;
  const pick = free[Math.floor(Math.random() * free.length)];
  return { x: pick % G, y: Math.floor(pick / G) };
}

// Advance the snake by one cell. Returns nothing; may end the game.
function step() {
  // Take the next buffered turn (never a 180 relative to the current direction).
  while (state.queue.length) {
    const d = state.queue.shift();
    if (d.x === -state.dir.x && d.y === -state.dir.y) continue;
    state.dir = d;
    break;
  }

  const wrap = CONFIG.difficulties[state.difficulty].wrap;
  const head = state.snake[0];
  let nx = head.x + state.dir.x;
  let ny = head.y + state.dir.y;

  if (wrap) {
    nx = (nx + G) % G;
    ny = (ny + G) % G;
  } else if (nx < 0 || ny < 0 || nx >= G || ny >= G) {
    return gameOver();
  }

  const next = { x: nx, y: ny };
  const eatFood = sameCell(next, state.food);
  const eatGolden = sameCell(next, state.golden);
  const grow = eatFood || eatGolden;

  // The tail cell is vacated this tick unless we're growing, so it's safe to enter.
  const bodyToCheck = grow ? state.snake.length : state.snake.length - 1;
  for (let i = 0; i < bodyToCheck; i++) {
    if (sameCell(state.snake[i], next)) return gameOver();
  }

  state.snake.unshift(next);
  if (!grow) state.snake.pop();

  if (eatFood || eatGolden) {
    const gold = eatGolden;
    state.score += gold ? CONFIG.pointsGolden : CONFIG.pointsFood;
    state.eaten++;
    if (state.score > state.best) {
      state.best = state.score;
      storeSet(bestKey(), state.best);
    }
    burst(next.x + 0.5, next.y + 0.5, gold ? CONFIG.colors.golden : CONFIG.colors.food, gold ? 28 : 14);
    gold ? Sound.golden() : Sound.eat();

    if (gold) {
      state.golden = null;
    } else {
      state.food = null;
      state.food = randomEmptyCell();
      if (!state.golden && Math.random() < CONFIG.golden.chance) {
        const cell = randomEmptyCell();
        if (cell) state.golden = { x: cell.x, y: cell.y, left: CONFIG.golden.lifetimeMs };
      }
    }
    state.tickMs = tickInterval();
    updateHud();
    if (!state.food) return gameOver(true); // board completely full
  }
}

function updateGolden(dt) {
  if (!state.golden) return;
  state.golden.left -= dt;
  if (state.golden.left <= 0) state.golden = null;
}

function gameOver(won) {
  state.screen = 'over';
  state.won = !!won;
  state.newRecord = state.score > state.bestAtStart;
  if (state.score > state.best) state.best = state.score;
  storeSet(bestKey(), state.best);
  state.shake = CONFIG.gameOverShakeMs;
  state.overAt = performance.now();
  state.overShown = false;
  const head = state.snake[0];
  burst(head.x + 0.5, head.y + 0.5, '#ef4444', 24);
  Sound.over();
  updateHud();
}

/* =====================================================================
   5. Particles
   Positions are in grid units so they survive window resizes.
   ===================================================================== */
function burst(x, y, color, count) {
  for (let i = 0; i < count; i++) {
    const a = Math.random() * Math.PI * 2;
    const speed = 1.5 + Math.random() * 4.5; // cells per second
    state.particles.push({
      x, y, vx: Math.cos(a) * speed, vy: Math.sin(a) * speed,
      life: 450 + Math.random() * 350, max: 800, size: 0.06 + Math.random() * 0.09, color,
    });
  }
}

function updateParticles(dt) {
  const s = dt / 1000;
  for (const p of state.particles) {
    p.x += p.vx * s;
    p.y += p.vy * s;
    p.vx *= 0.96;
    p.vy *= 0.96;
    p.life -= dt;
  }
  state.particles = state.particles.filter((p) => p.life > 0);
}

/* =====================================================================
   6. Sound (Web Audio, no files)
   ===================================================================== */
const Sound = {
  ctx: null,
  muted: storeGet('snake.muted', '0') === '1',

  // Browsers only allow audio after a user gesture, so create lazily.
  ensure() {
    if (!this.ctx) {
      const AC = window.AudioContext || window.webkitAudioContext;
      if (!AC) return;
      try { this.ctx = new AC(); } catch (e) { return; }
    }
    if (this.ctx.state === 'suspended') this.ctx.resume();
  },

  tone(freq, delay, dur, type, vol, endFreq) {
    if (this.muted || !this.ctx) return;
    const t = this.ctx.currentTime + delay;
    const osc = this.ctx.createOscillator();
    const gain = this.ctx.createGain();
    osc.type = type;
    osc.frequency.setValueAtTime(freq, t);
    if (endFreq) osc.frequency.exponentialRampToValueAtTime(endFreq, t + dur);
    gain.gain.setValueAtTime(0.0001, t);
    gain.gain.exponentialRampToValueAtTime(vol, t + 0.01);
    gain.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    osc.connect(gain).connect(this.ctx.destination);
    osc.start(t);
    osc.stop(t + dur + 0.02);
  },

  eat()    { this.tone(520, 0, 0.09, 'square', 0.07, 780); },
  golden() { [880, 1175, 1568].forEach((f, i) => this.tone(f, i * 0.08, 0.22, 'sine', 0.12)); },
  over()   { this.tone(220, 0, 0.55, 'sawtooth', 0.12, 55); },

  toggle() {
    this.muted = !this.muted;
    storeSet('snake.muted', this.muted ? '1' : '0');
    updateMuteButton();
  },
};

/* =====================================================================
   7. Rendering
   ===================================================================== */
const canvas = $('game');
const ctx = canvas.getContext('2d');
const view = { size: 0, dpr: 1 };

// Match the backing store to the displayed size × devicePixelRatio for crisp output.
function resizeCanvas() {
  const rect = canvas.getBoundingClientRect();
  const size = Math.round(rect.width);
  if (size < 1) return;
  const px = Math.round(size * (window.devicePixelRatio || 1));
  if (canvas.width !== px || canvas.height !== px) {
    canvas.width = px;
    canvas.height = px;
  }
  view.size = size;
  view.dpr = px / size;
}

function render(ts) {
  if (!view.size) return;
  const size = view.size;
  const cell = size / G;
  const c = CONFIG.colors;

  ctx.setTransform(view.dpr, 0, 0, view.dpr, 0, 0);
  ctx.fillStyle = c.bg;
  ctx.fillRect(0, 0, size, size);

  ctx.save();
  if (state.shake > 0) {
    const amp = (state.shake / CONFIG.gameOverShakeMs) * cell * 0.4;
    ctx.translate((Math.random() - 0.5) * 2 * amp, (Math.random() - 0.5) * 2 * amp);
  }

  drawGrid(size, cell);
  drawFood(cell, ts);
  drawGolden(cell, ts);
  drawSnake(cell);
  drawParticles(cell);

  ctx.restore();
}

function drawGrid(size, cell) {
  ctx.strokeStyle = CONFIG.colors.grid;
  ctx.lineWidth = 1;
  ctx.beginPath();
  for (let i = 1; i < G; i++) {
    const p = Math.round(i * cell) + 0.5;
    ctx.moveTo(p, 0); ctx.lineTo(p, size);
    ctx.moveTo(0, p); ctx.lineTo(size, p);
  }
  ctx.stroke();
}

function drawSnake(cell) {
  const snake = state.snake;
  const n = snake.length;
  const dead = state.screen === 'over';
  if (dead) ctx.globalAlpha = 0.8;

  for (let i = n - 1; i >= 0; i--) {
    const seg = snake[i];
    const t = n > 1 ? i / (n - 1) : 0;
    const pad = cell * (0.07 + 0.1 * t);        // tail is slightly thinner
    const color = mixColor(HEAD_RGB, TAIL_RGB, t);
    const x = seg.x * cell, y = seg.y * cell;

    ctx.fillStyle = color;

    // Connector to the segment behind it so the body looks continuous.
    if (i < n - 1) {
      const nxt = snake[i + 1];
      const dx = nxt.x - seg.x, dy = nxt.y - seg.y;
      if (Math.abs(dx) <= 1 && Math.abs(dy) <= 1) { // skip across wrap-around edges
        const cx = x + cell / 2, cy = y + cell / 2;
        const half = cell / 2 - pad;
        if (dx !== 0) ctx.fillRect(Math.min(cx, cx + dx * cell), cy - half, cell, half * 2);
        else ctx.fillRect(cx - half, Math.min(cy, cy + dy * cell), half * 2, cell);
      }
    }

    roundedRect(ctx, x + pad, y + pad, cell - pad * 2, cell - pad * 2, cell * 0.32);
    ctx.fill();
  }

  // Head with eyes that face the direction of movement.
  const h = snake[0];
  drawEyes(h.x * cell + cell / 2, h.y * cell + cell / 2, cell, state.dir);
  ctx.globalAlpha = 1;
}

function drawEyes(cx, cy, cell, dir) {
  const px = -dir.y, py = dir.x;                 // perpendicular to heading
  const fwd = cell * 0.14, side = cell * 0.2, r = cell * 0.13;
  for (const s of [-1, 1]) {
    const ex = cx + dir.x * fwd + px * side * s;
    const ey = cy + dir.y * fwd + py * side * s;
    ctx.fillStyle = '#ffffff';
    ctx.beginPath(); ctx.arc(ex, ey, r, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = '#0b0f1a';
    ctx.beginPath(); ctx.arc(ex + dir.x * r * 0.4, ey + dir.y * r * 0.4, r * 0.55, 0, Math.PI * 2); ctx.fill();
  }
}

function drawFood(cell, ts) {
  const f = state.food;
  if (!f) return;
  const cx = f.x * cell + cell / 2, cy = f.y * cell + cell / 2;
  const pulse = 1 + 0.1 * Math.sin(ts / 220);
  const r = cell * 0.32 * pulse;
  ctx.save();
  ctx.shadowColor = CONFIG.colors.food;
  ctx.shadowBlur = cell * (0.5 + 0.2 * Math.sin(ts / 220));
  ctx.fillStyle = CONFIG.colors.food;
  ctx.beginPath(); ctx.arc(cx, cy, r, 0, Math.PI * 2); ctx.fill();
  ctx.restore();
  ctx.fillStyle = 'rgba(255, 255, 255, 0.55)';
  ctx.beginPath(); ctx.arc(cx - r * 0.35, cy - r * 0.35, r * 0.25, 0, Math.PI * 2); ctx.fill();
}

function drawGolden(cell, ts) {
  const g = state.golden;
  if (!g) return;
  const cx = g.x * cell + cell / 2, cy = g.y * cell + cell / 2;
  const frac = Math.max(0, g.left / CONFIG.golden.lifetimeMs);
  const blinking = g.left < CONFIG.golden.blinkMs;
  const alpha = blinking ? 0.45 + 0.55 * Math.abs(Math.sin(ts / 90)) : 1;
  const r = cell * 0.34 * (1 + 0.06 * Math.sin(ts / 130));

  ctx.save();
  ctx.globalAlpha = alpha;

  // Glowing body
  ctx.shadowColor = CONFIG.colors.golden;
  ctx.shadowBlur = cell * (0.8 + 0.5 * Math.sin(ts / 160));
  const grad = ctx.createRadialGradient(cx - r * 0.3, cy - r * 0.3, r * 0.1, cx, cy, r);
  grad.addColorStop(0, CONFIG.colors.goldenLight);
  grad.addColorStop(1, CONFIG.colors.golden);
  ctx.fillStyle = grad;
  ctx.beginPath(); ctx.arc(cx, cy, r, 0, Math.PI * 2); ctx.fill();
  ctx.shadowBlur = 0;

  // Countdown ring that drains clockwise over the apple's lifetime
  ctx.strokeStyle = CONFIG.colors.golden;
  ctx.lineWidth = Math.max(2, cell * 0.08);
  ctx.lineCap = 'round';
  ctx.beginPath();
  ctx.arc(cx, cy, cell * 0.46, -Math.PI / 2, -Math.PI / 2 + Math.PI * 2 * frac);
  ctx.stroke();

  // Shimmer: a sparkle orbiting the apple
  const a = ts / 400;
  const sx = cx + Math.cos(a) * r * 0.9, sy = cy + Math.sin(a) * r * 0.9;
  const sr = cell * 0.09 * (0.6 + 0.4 * Math.abs(Math.sin(ts / 110)));
  ctx.fillStyle = '#ffffff';
  ctx.beginPath();
  ctx.moveTo(sx, sy - sr * 2); ctx.lineTo(sx + sr * 0.5, sy - sr * 0.5);
  ctx.lineTo(sx + sr * 2, sy); ctx.lineTo(sx + sr * 0.5, sy + sr * 0.5);
  ctx.lineTo(sx, sy + sr * 2); ctx.lineTo(sx - sr * 0.5, sy + sr * 0.5);
  ctx.lineTo(sx - sr * 2, sy); ctx.lineTo(sx - sr * 0.5, sy - sr * 0.5);
  ctx.closePath(); ctx.fill();

  ctx.restore();
}

function drawParticles(cell) {
  for (const p of state.particles) {
    const k = p.life / p.max;
    ctx.globalAlpha = Math.max(0, Math.min(1, k));
    ctx.fillStyle = p.color;
    ctx.beginPath();
    ctx.arc(p.x * cell, p.y * cell, p.size * cell * Math.max(0.2, k), 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.globalAlpha = 1;
}

/* =====================================================================
   8. UI (HUD + overlay screens)
   ===================================================================== */
const ui = {
  score: $('score'), best: $('best'), level: $('level'),
  start: $('startScreen'), pause: $('pauseScreen'), over: $('overScreen'),
  muteBtn: $('muteBtn'), pauseBtn: $('pauseBtn'),
};

function updateHud() {
  ui.score.textContent = state.score;
  ui.best.textContent = state.best;
  ui.level.textContent = level();
}

function updateMuteButton() {
  ui.muteBtn.classList.toggle('muted', Sound.muted);
  ui.muteBtn.setAttribute('aria-label', Sound.muted ? 'Unmute' : 'Mute');
}

function showScreen() {
  ui.start.hidden = state.screen !== 'start';
  ui.pause.hidden = state.screen !== 'paused';
  ui.over.hidden = !(state.screen === 'over' && state.overShown);
}

function showGameOver() {
  state.overShown = true;
  $('overTitle').textContent = state.won ? 'You win!' : 'Game over';
  $('finalScore').textContent = state.score;
  $('finalBest').textContent = state.best;
  $('newRecord').hidden = !state.newRecord;
  showScreen();
}

function selectDifficulty(key) {
  if (!CONFIG.difficulties[key]) return;
  state.difficulty = key;
  storeSet('snake.difficulty', key);
  document.querySelectorAll('#difficulty button').forEach((b) => {
    b.setAttribute('aria-checked', String(b.dataset.diff === key));
  });
  $('diffHint').textContent = CONFIG.difficulties[key].hint;
  resetGame(); // refreshes the best score + board preview for this difficulty
}

function cycleDifficulty(delta) {
  const keys = Object.keys(CONFIG.difficulties);
  const i = (keys.indexOf(state.difficulty) + delta + keys.length) % keys.length;
  selectDifficulty(keys[i]);
}

/* =====================================================================
   9. Game flow (start / pause / loop)
   ===================================================================== */
function startGame() {
  Sound.ensure();
  resetGame();
  state.screen = 'playing';
  showScreen();
}

function togglePause() {
  if (state.screen === 'playing') state.screen = 'paused';
  else if (state.screen === 'paused') state.screen = 'playing';
  else return;
  showScreen();
}

function pauseIfPlaying() {
  if (state.screen === 'playing') { state.screen = 'paused'; showScreen(); }
}

/* =====================================================================
   10. Input handling
   ===================================================================== */
// Buffer a turn. Each press is validated against the *last queued* direction
// (not just the current one), so two quick presses like Up then Left both
// take effect on consecutive ticks, and a reversal can never slip through.
function queueDirection(d) {
  if (state.screen !== 'playing') return;
  const last = state.queue.length ? state.queue[state.queue.length - 1] : state.dir;
  if (d.x === last.x && d.y === last.y) return;      // same direction
  if (d.x === -last.x && d.y === -last.y) return;    // 180° reversal
  if (state.queue.length >= CONFIG.maxQueuedInputs) return;
  state.queue.push(d);
}

const KEY_DIRS = {
  ArrowUp: 'up', ArrowDown: 'down', ArrowLeft: 'left', ArrowRight: 'right',
  w: 'up', s: 'down', a: 'left', d: 'right',
};

window.addEventListener('keydown', (e) => {
  if (e.ctrlKey || e.metaKey || e.altKey) return;
  const key = e.key.length === 1 ? e.key.toLowerCase() : e.key;
  Sound.ensure();

  if (KEY_DIRS[key]) {
    e.preventDefault();
    const name = KEY_DIRS[key];
    if (state.screen === 'playing') queueDirection(DIRS[name]);
    else if (state.screen === 'start' && !e.repeat) {
      if (name === 'left' || name === 'up') cycleDifficulty(-1);
      else cycleDifficulty(1);
    }
    return;
  }
  if (e.repeat) return;

  if (key === 'Enter') {
    if (state.screen === 'start' || (state.screen === 'over' && state.overShown)) {
      e.preventDefault();
      startGame();
    }
  } else if (key === ' ' || key === 'p') {
    e.preventDefault();
    togglePause();
  } else if (key === 'm') {
    Sound.toggle();
  } else if (state.screen === 'start' && '123'.includes(key) && key !== '') {
    selectDifficulty(Object.keys(CONFIG.difficulties)[Number(key) - 1]);
  }
});

// Swipe gestures on the canvas
let touchPoint = null;
canvas.addEventListener('touchstart', (e) => {
  const t = e.changedTouches[0];
  touchPoint = { x: t.clientX, y: t.clientY };
  Sound.ensure();
  e.preventDefault();
}, { passive: false });
canvas.addEventListener('touchmove', (e) => {
  e.preventDefault();
  if (!touchPoint) return;
  const t = e.changedTouches[0];
  const dx = t.clientX - touchPoint.x, dy = t.clientY - touchPoint.y;
  if (Math.max(Math.abs(dx), Math.abs(dy)) < CONFIG.swipeMinPx) return;
  const name = Math.abs(dx) > Math.abs(dy) ? (dx > 0 ? 'right' : 'left') : (dy > 0 ? 'down' : 'up');
  queueDirection(DIRS[name]);
  touchPoint = { x: t.clientX, y: t.clientY }; // allow chained swipes in one gesture
}, { passive: false });
canvas.addEventListener('touchend', () => { touchPoint = null; });
canvas.addEventListener('touchcancel', () => { touchPoint = null; });

// On-screen arrow buttons
document.querySelectorAll('.dpad button').forEach((btn) => {
  btn.addEventListener('pointerdown', (e) => {
    e.preventDefault();
    Sound.ensure();
    queueDirection(DIRS[btn.dataset.dir]);
  });
});

// Buttons and overlays (blur afterwards so Space/Enter don't re-trigger them)
function onClick(el, fn) { el.addEventListener('click', () => { el.blur(); fn(); }); }
onClick($('startBtn'), startGame);
onClick($('againBtn'), startGame);
onClick($('resumeBtn'), togglePause);
onClick(ui.pauseBtn, togglePause);
onClick(ui.muteBtn, () => { Sound.ensure(); Sound.toggle(); });
document.querySelectorAll('#difficulty button').forEach((b) => {
  b.addEventListener('click', () => { b.blur(); selectDifficulty(b.dataset.diff); });
});

// Auto-pause when the tab or window loses focus.
document.addEventListener('visibilitychange', () => { if (document.hidden) pauseIfPlaying(); });
window.addEventListener('blur', pauseIfPlaying);

// Keep the canvas sharp on resize, zoom, or rotation.
window.addEventListener('resize', resizeCanvas);
if (window.ResizeObserver) new ResizeObserver(resizeCanvas).observe(canvas);

/* =====================================================================
   11. Main loop
   One requestAnimationFrame loop for the whole page lifetime (started once,
   never restarted). Snake movement uses a fixed-timestep accumulator, so speed
   is identical on 60Hz, 144Hz or any other display.
   ===================================================================== */
let lastTs = 0;
function frame(ts) {
  const dt = Math.min(ts - lastTs, CONFIG.maxFrameMs);
  lastTs = ts;

  if (state.screen === 'playing') {
    state.acc += dt;
    updateGolden(dt); // runs only while playing, so pausing freezes the countdown
    while (state.acc >= state.tickMs && state.screen === 'playing') {
      state.acc -= state.tickMs;
      step();
    }
  }

  if (state.screen !== 'paused') {
    updateParticles(dt);
    state.shake = Math.max(0, state.shake - dt);
  }

  if (state.screen === 'over' && !state.overShown && ts - state.overAt > CONFIG.gameOverOverlayDelayMs) {
    showGameOver();
  }

  render(ts);
  requestAnimationFrame(frame);
}

/* =====================================================================
   12. Init
   ===================================================================== */
(function init() {
  const saved = storeGet('snake.difficulty', CONFIG.defaultDifficulty);
  selectDifficulty(CONFIG.difficulties[saved] ? saved : CONFIG.defaultDifficulty);
  updateMuteButton();
  showScreen();
  resizeCanvas();
  requestAnimationFrame(frame);
})();
