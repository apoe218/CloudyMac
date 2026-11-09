// Refreshes data/news.json from the BBC Sport Liverpool RSS feed. No API key needed.
// Keeps hand-added items (manual:true) and replaces the rest.
import { readFile, writeFile } from 'node:fs/promises';
const FEED = 'https://feeds.bbci.co.uk/sport/football/teams/liverpool/rss.xml';
const FILE = new URL('../data/news.json', import.meta.url);
const tag = (x, t) => (x.match(new RegExp(`<${t}[^>]*>(?:<!\\[CDATA\\[)?([\\s\\S]*?)(?:\\]\\]>)?</${t}>`)) || [])[1]?.trim() || '';
const TRANSFER = /\b(transfers?|sign(?:s|ed|ing|ings)?|bids?|fee|loan|contract|deal|target(?:s|ed)?|£\d+|market|window|release clause)\b/i;
const xml = process.env.FEED_FILE
  ? await readFile(process.env.FEED_FILE, 'utf8') // offline testing
  : await (await fetch(FEED, { headers: { 'user-agent': 'kop-daily/1.0' } })).text();
const fresh = [...xml.matchAll(/<item>([\s\S]*?)<\/item>/g)].map(([, x]) => {
  const title = tag(x, 'title'), desc = tag(x, 'description');
  return { cat: TRANSFER.test(title + ' ' + desc) ? 'transfers' : 'team', title, src: 'BBC Sport', url: tag(x, 'link').replaceAll('&amp;', '&'), date: new Date(tag(x, 'pubDate') || Date.now()).toISOString() };
}).filter(i => i.title && /^https?:/.test(i.url)).slice(0, 25);
if (!fresh.length) { console.error('No items parsed; leaving news.json untouched'); process.exit(0); }
const old = JSON.parse(await readFile(FILE, 'utf8'));
const manual = (old.items || []).filter(i => i.manual);
const items = [...fresh, ...manual].sort((a, b) => b.date.localeCompare(a.date));
await writeFile(FILE, JSON.stringify({ updated: new Date().toISOString(), items }, null, 1) + '\n');
console.log(`Wrote ${items.length} items (${fresh.length} fresh)`);
