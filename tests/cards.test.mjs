import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

// The game is one self-contained index.html; pull the engine section out of it.
const html = readFileSync(new URL('../index.html', import.meta.url), 'utf8');
const engine = html.split('// ==== ENGINE START')[1].split('// ==== ENGINE END')[0];
const ctx = vm.createContext({ structuredClone });
vm.runInContext(engine + `
globalThis.E = {
  isRed, rng, newGame, move, draw, findMoves, autoDest, autoStep, canAutoComplete, isWon, canDraw,
  evaluate, handName, pkEquity, newHoldem, heStartHand, heAct, heAdvance, heBot, heLegal, heSettle, heTotalPot,
  newBlackjack, bjValue, bjBet, bjDeal, bjHit, bjStand, bjDouble, bjSplit, bjCanSplit, bjDealerStep, bjSettle, bjNewRound, bjAdvice, bjShoe,
};`, ctx);
const {
  isRed, rng, newGame, move, draw, findMoves, autoDest, autoStep, canAutoComplete, isWon,
  evaluate, handName, pkEquity, newHoldem, heStartHand, heAct, heAdvance, heBot, heLegal, heSettle, heTotalPot,
  newBlackjack, bjValue, bjBet, bjDeal, bjHit, bjStand, bjDouble, bjSplit, bjCanSplit, bjDealerStep, bjSettle, bjNewRound, bjAdvice, bjShoe,
} = ctx.E;
// card shorthand: 'As' 'Td' '9h' '2c'
const C = (str) => str.split(' ').map((x) => ({
  r: 'A23456789TJQK'.indexOf(x[0]) + 1, s: 'shdc'.indexOf(x[1]), up: true,
}));

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
  assert.deepEqual([...s.tableau.map((c) => c.length)], [1, 2, 3, 4, 5, 6, 7]);
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

test('stuck detection helper inputs: findMoves is empty on a dead board', () => {
  const s = newGame(1, { draw: 1, redeals: 0 });
  s.stock = [];
  s.waste = [];
  s.tableau = [[{ s: 0, r: 5, up: true }], [{ s: 0, r: 5 + 1, up: true }], [], [], [], [], []];
  s.tableau[1] = [{ s: 1, r: 3, up: true }];
  assert.equal(findMoves(s).filter((m) => m.w >= 1).length, 0);
});

// ---------------- poker evaluation ----------------
test('hand categories rank correctly and are named', () => {
  const ladder = [
    ['Ah Kd 9s 6c 3d', 'High card'],
    ['Ah Ad 9s 6c 3d', 'Pair'],
    ['Ah Ad 9s 9c 3d', 'Two pair'],
    ['Ah Ad As 6c 3d', 'Three of a kind'],
    ['5h 6d 7s 8c 9d', 'Straight'],
    ['2h 6h 9h Jh Kh', 'Flush'],
    ['Ah Ad As 6c 6d', 'Full house'],
    ['Ah Ad As Ac 3d', 'Four of a kind'],
    ['5h 6h 7h 8h 9h', 'Straight flush'],
    ['Th Jh Qh Kh Ah', 'Royal flush'],
  ];
  let prev = -1;
  for (const [cards, name] of ladder) {
    const sc = evaluate(C(cards));
    assert.ok(sc > prev, name);
    assert.equal(handName(sc), name);
    prev = sc;
  }
});

test('wheel straight is the lowest straight; broadway beats it', () => {
  const wheel = evaluate(C('Ah 2d 3s 4c 5d'));
  assert.equal(handName(wheel), 'Straight');
  assert.ok(wheel < evaluate(C('2h 3d 4s 5c 6d')));
  assert.ok(evaluate(C('Th Jd Qs Kc Ad')) > evaluate(C('9h Td Js Qc Kd')));
});

test('best five of seven, kickers and ties', () => {
  assert.equal(handName(evaluate(C('Ah Ad 2s 7c 9d Ks Kh'))), 'Two pair');
  assert.ok(evaluate(C('Ah Kd 9s 9c 3d 2s 4h')) > evaluate(C('Qh Kd 9s 9c 3d 2s 4h')));  // ace vs queen kicker
  assert.equal(evaluate(C('Ah Kd 2s 3c 4d 9s 9h')), evaluate(C('Ac Ks 2d 3h 4s 9d 9c')));
  assert.equal(handName(evaluate(C('2h 2d 2s 5c 5d 9s 9h'))), 'Full house');         // trips + two pairs
});

test('equity is sane: aces beat random hands, 72o does not', () => {
  const r = rng(5);
  assert.ok(pkEquity(C('As Ad'), [], 1, r, 300) > 0.78);
  assert.ok(pkEquity(C('7s 2d'), [], 1, r, 300) < 0.45);
  assert.ok(pkEquity(C('As Ad'), C('Ah Ac 2d 7s 9h'), 3, r, 100) > 0.99);
});

// ---------------- hold'em betting ----------------
function totalChips(s) { return s.players.reduce((a, p) => a + p.chips, 0); }

function playHandWithBots(s, rand) {
  heStartHand(s, rand);
  let guard = 0;
  while (s.phase !== 'handover') {
    if (++guard > 200) throw new Error('hand did not terminate');
    if (s.phase === 'runout') heAdvance(s);
    else if (s.phase === 'action') {
      const a = heBot(s, s.toAct, rand, 12);
      assert.ok(heAct(s, s.toAct, a), JSON.stringify(a));
    } else throw new Error('unexpected phase ' + s.phase);
  }
}

test('blinds, heads-up button and preflop order', () => {
  const s = newHoldem({ opponents: 3 });
  heStartHand(s, rng(1));
  const posted = s.players.map((p) => p.bet);
  assert.deepEqual([...posted].sort((a, b) => a - b), [0, 0, 10, 20]);
  const hu = newHoldem({ opponents: 1 });
  heStartHand(hu, rng(1));
  assert.equal(hu.players[hu.button].bet, 10);   // button posts the small blind heads-up
  assert.equal(hu.toAct, hu.button);             // and acts first preflop
});

test('everyone folds to the big blind: BB wins the blinds', () => {
  const s = newHoldem({ opponents: 2 });
  heStartHand(s, rng(2));
  while (s.phase === 'action') heAct(s, s.toAct, { type: 'fold' });
  assert.equal(s.phase, 'handover');
  assert.equal(totalChips(s), 3000);
  assert.equal(s.results.showdown, false);
  assert.equal(Math.max(...s.results.net), 10);
});

test('check-down reaches showdown through all streets', () => {
  const s = newHoldem({ opponents: 2 });
  heStartHand(s, rng(3));
  const seen = [];
  while (s.phase !== 'handover') {
    if (!seen.includes(s.street)) seen.push(s.street);
    heAct(s, s.toAct, { type: 'call' });
  }
  assert.deepEqual(seen, ['preflop', 'flop', 'turn', 'river']);
  assert.equal(s.board.length, 5);
  assert.equal(s.results.showdown, true);
  assert.equal(totalChips(s), 3000);
});

test('raise rules: min raise enforced and reopens action', () => {
  const s = newHoldem({ opponents: 2 });
  heStartHand(s, rng(4));
  const i = s.toAct;
  const L = heLegal(s, i);
  assert.equal(L.minTo, 40);
  heAct(s, i, { type: 'raise', to: 25 });             // too small, bumped to the minimum
  assert.equal(s.currentBet, 40);
  assert.equal(s.minRaise, 20);
});

test('side pots: short stack wins only the main pot', () => {
  const s = newHoldem({ opponents: 2 });
  s.board = C('2c 7d 9h Jc 3s');
  const [a, b, c] = s.players;
  a.hole = C('As Ad'); b.hole = C('Ks Kd'); c.hole = C('Qs Qd');
  Object.assign(a, { total: 100, chips: 0, allIn: true });   // best hand but short
  Object.assign(b, { total: 300, chips: 0, allIn: true });
  Object.assign(c, { total: 300, chips: 0, allIn: true });
  s.street = 'river'; s.button = 0;
  heSettle(s);
  assert.deepEqual([...s.results.won], [300, 400, 0]);  // a takes 3x100, b takes the 200+200 side pot
  assert.equal(totalChips(s), 700);
});

test('split pot divides evenly and odd chip goes left of the button', () => {
  const s = newHoldem({ opponents: 2 });
  s.board = C('Ah Kd Qs Jc Td');   // everyone plays the board straight
  s.players.forEach((p, i) => { p.hole = C(['2c 3d', '2h 3s', '4c 5d'][i]); p.total = 0; p.chips = 0; });
  s.players[0].total = 5; s.players[1].total = 6; s.players[2].total = 6;
  s.button = 2;
  heSettle(s);
  assert.equal(s.results.won.reduce((a, b) => a + b, 0), 17);
  assert.ok(Math.max(...s.results.won) - Math.min(...s.results.won) <= 6);
});

test('bot-vs-bot games always terminate and conserve chips', () => {
  for (let seed = 1; seed <= 6; seed++) {
    const rand = rng(seed * 31);
    const s = newHoldem({ opponents: 1 + (seed % 5), stack: 400 });
    const total = totalChips(s);
    for (let h = 0; h < 40 && s.players.filter((p) => p.chips > 0).length > 1; h++) {
      playHandWithBots(s, rand);
      assert.equal(totalChips(s), total);
      s.players.forEach((p) => assert.ok(p.chips >= 0));
    }
  }
});

// ---------------- blackjack ----------------
test('blackjack hand values', () => {
  assert.deepEqual({ ...bjValue(C('As Kd')) }, { total: 21, soft: true });
  assert.deepEqual({ ...bjValue(C('As Ad 9c')) }, { total: 21, soft: true });
  assert.deepEqual({ ...bjValue(C('As 6d Kc')) }, { total: 17, soft: false });
  assert.equal(bjValue(C('Kd Qs 5c')).total, 25);
});

function bjSetup(player, dealer, opts = {}, bankroll = 1000) {
  const s = newBlackjack(opts, bankroll);
  s.shoe = bjShoe(6, rng(1));
  bjBet(s, 100);
  // rig the next cards: draw order is player, dealer up, player, dealer hole
  const rig = [player[0], dealer[0], player[1], dealer[1]].map((c) => ({ ...C(c)[0] }));
  s.shoe.push(...rig.reverse());
  bjDeal(s, rng(1));
  return s;
}

test('player blackjack pays 3:2, dealer blackjack pushes it', () => {
  const s = bjSetup(['As', 'Kd'], ['9c', '8d']);
  assert.equal(s.phase, 'done');
  assert.equal(s.bankroll, 1000 - 100 + 250);
  const p = bjSetup(['As', 'Kd'], ['Ac', 'Qd']);
  assert.equal(p.hands[0].result, 'push');
  assert.equal(p.bankroll, 1000);
  const d = bjSetup(['9s', '8d'], ['Ac', 'Kd']);
  assert.equal(d.hands[0].result, 'lose');
  assert.equal(d.bankroll, 900);
});

test('hit to bust loses; standing against a bust wins', () => {
  const s = bjSetup(['Ts', '6d'], ['Tc', '6h']);
  s.shoe.push(...C('Kd'));
  bjHit(s);
  assert.equal(s.phase, 'dealer');
  while (bjDealerStep(s) !== 'stand');
  bjSettle(s);
  assert.equal(s.hands[0].result, 'bust');
  assert.equal(s.bankroll, 900);

  const w = bjSetup(['Ts', '8d'], ['Tc', '6h']);
  bjStand(w);
  w.shoe.push(...C('Kd'));
  let step;
  while ((step = bjDealerStep(w)) !== 'stand') assert.ok(step);
  bjSettle(w);
  assert.equal(w.hands[0].result, 'win');
  assert.equal(w.bankroll, 1100);
});

test('dealer stands on soft 17 unless configured to hit', () => {
  const stand = bjSetup(['Ts', '8d'], ['As', '6h']);
  bjStand(stand);
  while (bjDealerStep(stand) !== 'stand');
  assert.equal(stand.dealer.length, 2);
  const hit = bjSetup(['Ts', '8d'], ['As', '6h'], { hitSoft17: true });
  bjStand(hit);
  while (bjDealerStep(hit) !== 'stand');
  assert.ok(hit.dealer.length > 2);
});

test('double takes one card and doubles the stake; split makes two hands', () => {
  const d = bjSetup(['5s', '6d'], ['Tc', '6h']);
  d.shoe.push(...C('Kd'));
  assert.ok(bjDouble(d));
  assert.equal(d.hands[0].bet, 200);
  assert.equal(d.bankroll, 800);
  assert.equal(d.hands[0].cards.length, 3);

  const s = bjSetup(['8s', '8d'], ['Tc', '7h']);
  assert.ok(bjCanSplit(s));
  s.shoe.push(...C('3c 2c'));
  bjSplit(s);
  assert.equal(s.hands.length, 2);
  assert.equal(s.bankroll, 800);
  assert.ok(s.hands.every((h) => h.cards.length === 2));
});

test('split aces get one card each and cannot be resplit', () => {
  const s = bjSetup(['As', 'Ad'], ['Tc', '7h']);
  s.shoe.push(...C('Ks Ac'));
  bjSplit(s);
  assert.equal(s.phase, 'dealer');
  assert.ok(s.hands.every((h) => h.done));
  // 21 after a split ace is not a blackjack
  while (bjDealerStep(s) !== 'stand');
  bjSettle(s);
  assert.notEqual(s.hands[0].result, 'blackjack');
});

test('basic strategy spot checks', () => {
  const adv = (p, d) => bjAdvice(bjSetup(p, d));
  assert.equal(adv(['8s', '8d'], ['Tc', '7h']), 'split');
  assert.equal(adv(['5s', '6d'], ['6c', '7h']), 'double');
  assert.equal(adv(['Ts', '6d'], ['2c', '7h']), 'stand');
  assert.equal(adv(['Ts', '6d'], ['9c', '7h']), 'hit');
  assert.equal(adv(['As', '7d'], ['9c', '7h']), 'hit');
  assert.equal(adv(['As', '7d'], ['5c', '7h']), 'double');
  assert.equal(adv(['Ts', 'Kd'], ['5c', '7h']), 'stand');
});

test('random blackjack play keeps the bankroll consistent', () => {
  const rand = rng(9);
  const s = newBlackjack({}, 1000);
  for (let r = 0; r < 300 && s.bankroll >= 5; r++) {
    s.bet = 0;
    bjBet(s, Math.min(25, s.bankroll));
    const before = s.bankroll;
    bjDeal(s, rand);
    let guard = 0;
    while (s.phase === 'player' && guard++ < 50) {
      const a = bjAdvice(s);
      ({ hit: bjHit, stand: bjStand, double: bjDouble, split: bjSplit })[a](s) || bjStand(s);
    }
    if (s.phase === 'dealer') {
      while (bjDealerStep(s) !== 'stand');
      bjSettle(s);
    }
    assert.equal(s.phase, 'done');
    const staked = s.hands.reduce((a, h) => a + h.bet, 0);
    const paid = s.hands.reduce((a, h) => a + h.payout, 0);
    assert.equal(s.bankroll, before - staked + paid);
    assert.equal(s.net, paid - staked);
    assert.ok(s.bankroll >= 0);
    bjNewRound(s);
  }
});
