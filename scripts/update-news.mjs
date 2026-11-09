// Refreshes data/news.json (the offline fallback snapshot the app uses when live feeds fail).
// The app itself fetches feeds live in the browser; this keeps a recent copy in the repo.
import { readFile, writeFile } from 'node:fs/promises';
const gn = q => 'https://news.google.com/rss/search?q=' + encodeURIComponent(q) + '&hl=en-GB&gl=GB&ceid=GB:en';
const FEEDS = [
  { url: 'https://feeds.bbci.co.uk/sport/football/teams/liverpool/rss.xml', cat: 'team', src: 'BBC Sport' },
  { url: gn('Liverpool FC transfer news when:7d'), cat: 'transfers' },
  { url: gn('Liverpool FC injury news when:7d'), cat: 'injury' },
];
const FILE = new URL('../data/news.json', import.meta.url);
const dec = s => s.replaceAll('&amp;', '&').replaceAll('&lt;', '<').replaceAll('&gt;', '>').replaceAll('&quot;', '"').replaceAll('&#39;', "'");
const tag = (x, t) => dec((x.match(new RegExp(`<${t}[^>]*>(?:<!\\[CDATA\\[)?([\\s\\S]*?)(?:\\]\\]>)?</${t}>`)) || [])[1]?.trim() || '');
async function get(f) {
  const xml = process.env.FEED_FILE ? await readFile(process.env.FEED_FILE, 'utf8')
    : await (await fetch(f.url, { headers: { 'user-agent': 'kop-daily/1.0' } })).text();
  return [...xml.matchAll(/<item>([\s\S]*?)<\/item>/g)].map(([, x]) => {
    let title = tag(x, 'title'), src = f.src || tag(x, 'source');
    const m = title.match(/^(.*) - ([^-]{2,40})$/);
    if (!f.src && m) { title = m[1]; src = src || m[2]; }
    return { cat: f.cat, title, src: src || 'News', url: tag(x, 'link'), date: new Date(tag(x, 'pubDate') || Date.now()).toISOString() };
  }).filter(i => i.title && /^https?:/.test(i.url)).slice(0, 15);
}
const fresh = [];
for (const f of FEEDS) { try { fresh.push(...await get(f)); } catch (e) { console.error('feed failed', f.url, e.message); } if (process.env.FEED_FILE) break; }
if (!fresh.length) { console.error('No items parsed; leaving news.json untouched'); process.exit(0); }
const old = JSON.parse(await readFile(FILE, 'utf8'));
const manual = (old.items || []).filter(i => i.manual);
const items = [...fresh, ...manual].sort((a, b) => b.date.localeCompare(a.date));
await writeFile(FILE, JSON.stringify({ updated: new Date().toISOString(), items }, null, 1) + '\n');
console.log(`Wrote ${items.length} items (${fresh.length} fresh)`);
