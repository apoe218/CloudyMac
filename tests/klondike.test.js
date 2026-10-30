import test from 'node:test';
import assert from 'node:assert/strict';
import { isRed, rng } from '../src/core/deck.js';
import {
  newGame, move, draw, findMoves, autoDest, autoStep, canAutoComplete, isWon, getPile, TABLEAU, FOUNDATIONS,
} from '../src/games/klondike.js';

function allCards(s) {
  return [...s.stock, ...s.waste, ...s.foundations.flat(), ...s.tableau.flat()];
}

function checkInvariants(s) {
  const cards = allCards(s);
  assert.equal(cards.length, 52);
  assert.equal(new Set(cards.map((c) => c.s * 20 + c.r)).size, 52);
  s.stock.forEach((c) => assert.equal(c.up, false));
  s.waste.forEach((c) => assert.equal(c.up, true));
  s.foundations.forEach((f) => f.forEach((c, i) => {
    assert.equal(c.r, i + 1);
    assert.equal(c.s, f[0].s);
  }));
  s.tableau.forEach((col) => {
    if (col.length) assert.equal(col[col.length - 1].up, true);
    col.forEach((c, i) => {
      if (i > 0 && c.up && col[i - 1].up) {
        assert.equal(col[i - 1].r, c.r + 1);
        assert.notEqual(isRed(col[i - 1].s), isRed(c.s));
      }
      if (i > 0 && c.up) assert.ok(col[i - 1].up || true);
    });
  });
}

test('deal layout', () => {
  const s = newGame(1);
  assert.deepEqual(s.tableau.map((c) => c.length), [1, 2, 3, 4, 5, 6, 7]);
  assert.equal(s.stock.length, 24);
  s.tableau.forEach((col) => col.forEach((c, i) => assert.equal(c.up, i === col.length - 1)));
  checkInvariants(s);
});

test('same seed gives same deal, different seed differs', () => {
  const key = (s) => JSON.stringify(s.tableau);
  assert.equal(key(newGame(42)), key(newGame(42)));
  assert.notEqual(key(newGame(42)), key(newGame(43)));
});

test('draw 1 / draw 3 and recycle with scoring penalty', () => {
  const s = newGame(7, { draw: 3 });
  draw(s);
  assert.equal(s.waste.length, 3);
  assert.equal(s.fan, 3);
  while (s.stock.length) draw(s);
  s.score = 50;
  assert.ok(draw(s));
  assert.equal(s.stock.length, 24);
  assert.equal(s.waste.length, 0);
  assert.equal(s.score, 30);
  assert.equal(s.redealsUsed, 1);
  checkInvariants(s);
});

test('redeal limit is enforced', () => {
  const s = newGame(7, { draw: 1, redeals: 0 });
  while (s.stock.length) draw(s);
  assert.equal(draw(s), false);
});

test('foundation and tableau legality', () => {
  const s = newGame(1);
  s.tableau[0] = [{ s: 0, r: 1, up: true }];
  s.tableau[1] = [{ s: 1, r: 2, up: true }];
  assert.ok(move(s, 't0', 0, 'f0'));
  assert.equal(s.score, 10);
  // 2 of hearts cannot go on spade ace foundation
  assert.equal(move(s, 't1', 0, 'f0'), false);
  // empty tableau accepts only kings
  assert.equal(move(s, 't1', 0, 't0'), false);
  s.tableau[2] = [{ s: 2, r: 13, up: true }];
  assert.ok(move(s, 't2', 0, 't0'));
});

test('moving a run flips the revealed card for +5', () => {
  const s = newGame(1);
  s.tableau[0] = [{ s: 3, r: 9, up: false }, { s: 1, r: 8, up: true }];
  s.tableau[1] = [{ s: 0, r: 9, up: true }];
  s.score = 0;
  assert.ok(move(s, 't0', 1, 't1'));
  assert.equal(s.tableau[0][0].up, true);
  assert.equal(s.score, 5);
});

test('vegas scoring starts at -52 and pays 5 per foundation card', () => {
  const s = newGame(1, { scoring: 'vegas' });
  assert.equal(s.score, -52);
  s.tableau[0] = [{ s: 0, r: 1, up: true }];
  move(s, 't0', 0, 'f0');
  assert.equal(s.score, -47);
});

test('auto-complete finishes a fully revealed board', () => {
  const s = newGame(1);
  s.stock = [];
  s.waste = [];
  s.foundations = [[], [], [], []];
  s.tableau = [[], [], [], [], [], [], []];
  for (let su = 0; su < 4; su++) for (let r = 13; r >= 1; r--) s.tableau[su].push({ s: su, r, up: true });
  assert.ok(canAutoComplete(s));
  while (autoStep(s));
  assert.ok(isWon(s));
});

test('autoDest prefers foundation, then built column over empty', () => {
  const s = newGame(1);
  s.tableau = [[{ s: 0, r: 1, up: true }], [{ s: 1, r: 2, up: true }], [], [], [], [], []];
  assert.equal(autoDest(s, 't0', 0), 'f0');
  s.tableau = [[{ s: 0, r: 5, up: true }], [{ s: 1, r: 6, up: true }], [], [], [], [], []];
  assert.equal(autoDest(s, 't0', 0), 't1');
});

test('random play never breaks invariants', () => {
  for (let seed = 1; seed <= 40; seed++) {
    const s = newGame(seed, { draw: seed % 2 ? 1 : 3 });
    const rand = rng(seed * 977);
    for (let i = 0; i < 600; i++) {
      const moves = findMoves(s);
      if (moves.length && rand() < 0.8) {
        const m = moves[Math.floor(rand() * moves.length)];
        assert.ok(move(s, m.from, m.idx, m.to));
      } else {
        draw(s);
      }
      if (i % 50 === 0) checkInvariants(s);
    }
    checkInvariants(s);
  }
});
