export const SUITS = ['♠', '♥', '♦', '♣'];
export const RANKS = [null, 'A', '2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K'];
export const RANK_NAMES = [null, 'Ace', '2', '3', '4', '5', '6', '7', '8', '9', '10', 'Jack', 'Queen', 'King'];
export const SUIT_NAMES = ['spades', 'hearts', 'diamonds', 'clubs'];

export const isRed = (suit) => suit === 1 || suit === 2;

// mulberry32: small, fast, seedable PRNG so a deal can be replayed from its seed.
export function rng(seed) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// Cards are plain objects { s: suit 0-3, r: rank 1-13, up: face-up } so state clones cheaply.
export function shuffledDeck(seed) {
  const deck = [];
  for (let s = 0; s < 4; s++) for (let r = 1; r <= 13; r++) deck.push({ s, r, up: false });
  const rand = rng(seed);
  for (let i = deck.length - 1; i > 0; i--) {
    const j = Math.floor(rand() * (i + 1));
    [deck[i], deck[j]] = [deck[j], deck[i]];
  }
  return deck;
}
