# Card Table

Double-click `index.html` to play. It is one self-contained file with no install or server.

| Game | What you get |
|---|---|
| **Klondike** | Draw 1 or 3, standard / Vegas / no scoring, pass limits, undo, hints, auto-complete, daily deal |
| **Blackjack** | 1-8 decks, hit / stand / double / split, 3:2 or 6:5, dealer soft-17 rule, basic-strategy hints, bankroll |
| **Texas Hold'em** | No-limit vs 1-5 bots, side pots, all-in run-outs, equity-based hints, three blind levels |

Tap a card or button, or use the keys:

- Klondike: `Space` draw, `U` undo, `H` hint
- Blackjack: `H` hit, `S` stand, `D` double, `P` split, `Space` deal
- Hold'em: `F` fold, `C` check/call, `R` raise, `Space` next hand

Progress, bankroll, options and stats are saved in the browser. A link like `index.html#blackjack` opens a specific game.

Tests (Node 20+): `node --test tests/cards.test.mjs`
