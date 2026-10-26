#!/usr/bin/env python3
"""Build the H-Town Observer: a daily, personalised newspaper front page.

Standard library only. Run `python3 observer/build.py` and open observer/index.html.
Every source is fetched independently; if one is down its box says so and the
rest of the page still prints.
"""
import html
import json
import re
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).parent))
from crossword import render as crossword_render  # noqa: E402

try:
    from zoneinfo import ZoneInfo
    CT = ZoneInfo("America/Chicago")
except Exception:  # pragma: no cover - tzdata missing
    CT = timezone.utc

# ---------------------------------------------------------------------------
# Edit this block to tailor the paper.
# ---------------------------------------------------------------------------
UA = "Mozilla/5.0 (compatible; HTownObserver/1.0)"
HOUSTON = {"lat": 29.76, "lon": -95.37, "nws_grid": "HGX/65,97"}
ESPN = "https://site.api.espn.com/apis"
AGGIES_ID, LIVERPOOL_ID = "245", "364"
SEC_GROUP = "8"

FEEDS = {
    "scw": "https://spacecityweather.com/feed/",
    "nhc": "https://www.nhc.noaa.gov/index-at.xml",
    "houston": [
        ("Houston Public Media", "https://www.houstonpublicmedia.org/feed/"),
        ("KPRC 2", "https://www.click2houston.com/arc/outboundfeeds/rss/?outputType=xml"),
    ],
    "aggies": [
        ("ESPN", "https://site.api.espn.com/apis/site/v2/sports/football/college-football/news?team=245&limit=20"),
        ("ESPN", "https://www.espn.com/espn/rss/ncf/news"),
        ("Google News", "https://news.google.com/rss/search?q=" + quote('"Texas A&M" football when:3d')
         + "&hl=en-US&gl=US&ceid=US:en"),
    ],
    "sec": [
        ("ESPN", "https://site.api.espn.com/apis/site/v2/sports/football/college-football/news?limit=30"),
        ("Google News", "https://news.google.com/rss/search?q=" + quote("SEC football when:2d")
         + "&hl=en-US&gl=US&ceid=US:en"),
    ],
    "lfc": [
        ("ESPN", "https://site.api.espn.com/apis/site/v2/sports/soccer/eng.1/news?team=364&limit=20"),
        ("The Guardian", "https://www.theguardian.com/football/liverpool/rss"),
        ("Google News", "https://news.google.com/rss/search?q=" + quote("Liverpool FC when:2d")
         + "&hl=en-US&gl=US&ceid=US:en"),
    ],
    "football": [
        ("The Guardian", "https://www.theguardian.com/football/premierleague/rss"),
        ("The Guardian", "https://www.theguardian.com/football/championsleague/rss"),
        ("ESPN", "https://www.espn.com/espn/rss/soccer/news"),
        ("ESPN", "https://site.api.espn.com/apis/site/v2/sports/soccer/uefa.champions/news?limit=15"),
    ],
    "national": [
        ("BBC", "https://feeds.bbci.co.uk/news/world/us_and_canada/rss.xml"),
        ("The Guardian", "https://www.theguardian.com/us-news/rss"),
        ("NYT", "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml"),
    ],
    "world": [("BBC", "https://feeds.bbci.co.uk/news/world/rss.xml")],
}
# ---------------------------------------------------------------------------

PRINT = False  # True when building the one-page print edition


def fetch(url, tries=3, timeout=25):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(1.5 * (i + 1))
    raise RuntimeError(f"{url}: {last}")


def get_json(url):
    return json.loads(fetch(url))


def log(msg):
    print(msg, file=sys.stderr)


def esc(s):
    return html.escape(str(s or ""), quote=True)


def strip_html(s):
    s = re.sub(r"<(script|style).*?</\1>", "", s or "", flags=re.S | re.I)
    s = re.sub(r"</(p|div|li|h\d)>", "\n\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    s = html.unescape(s)
    return re.sub(r"[ \t\r\f\v]+", " ", s).strip()


def clip(s, n):
    s = re.sub(r"\s+", " ", s).strip()
    if len(s) <= n:
        return s
    cut = s[:n].rsplit(" ", 1)[0].rstrip(",;:-")
    return cut + "…"


# ---------------------------------------------------------------- RSS ------
NS = {
    "dc": "http://purl.org/dc/elements/1.1/",
    "content": "http://purl.org/rss/1.0/modules/ensite/",
}


def parse_rss(data, source):
    root = ET.fromstring(data)
    items = []
    for it in root.iter("item"):
        def t(tag):
            el = it.find(tag)
            return (el.text or "").strip() if el is not None and el.text else ""
        title, link = t("title"), t("link")
        if not title or not link:
            continue
        desc = strip_html(t("description"))
        try:
            when = parsedate_to_datetime(t("pubDate"))
            if when.tzinfo is None:
                when = when.replace(tzinfo=timezone.utc)
        except Exception:  # noqa: BLE001
            when = None
        src = source
        if source == "Google News":  # "Headline - Publisher"
            m = re.match(r"^(.*) - ([^-]+)$", title)
            if m:
                title, src = m.group(1), m.group(2)
            desc = ""  # Google's description is just the title repeated
        full = ""
        for el in it:
            if el.tag.endswith("}encoded"):
                full = el.text or ""
        items.append({"title": html.unescape(title), "link": link, "desc": desc,
                      "when": when, "source": src, "full": full})
    return items


SHARED_SEEN = set()  # stories already used anywhere on the page
BLOCK = re.compile(r"Engines of Our Ingenuity|Sponsored|Crossword|Wordle|Playoff Predictor|promo code|parlay|\bodds\b|\bbetting\b|\bpicks?\b", re.I)


def parse_espn_news(data, source):
    items = []
    for a in json.loads(data).get("articles", []):
        link = ((a.get("links") or {}).get("web") or {}).get("href")
        if not (a.get("headline") and link):
            continue
        try:
            when = datetime.fromisoformat(a["published"].replace("Z", "+00:00"))
        except Exception:  # noqa: BLE001
            when = None
        items.append({"title": a["headline"], "link": link, "desc": a.get("description") or "",
                      "when": when, "source": source, "full": ""})
    return items


def parse_feed(url, source):
    data = fetch(url)
    return parse_espn_news(data, source) if "/apis/" in url else parse_rss(data, source)


def article_text(url, want):
    """Best-effort: pull the first real paragraphs out of an article page."""
    page = fetch(url, tries=1, timeout=12).decode("utf-8", "ignore")
    page = re.sub(r"<(script|style|nav|footer|aside|figure|header|form|noscript)\b.*?</\1>", "", page,
                  flags=re.S | re.I)
    m = re.search(r"<article\b.*?</article>", page, flags=re.S | re.I)
    region = m.group(0) if m else page
    junk = re.compile(r"subscribe|cookie|sign up|newsletter|all rights reserved|advertisement|"
                      r"follow us|click here|read more|copyright|\u00a9|privacy", re.I)
    out, total = [], 0
    for raw in re.findall(r"<p\b[^>]*>(.*?)</p>", region, flags=re.S | re.I):
        t = strip_html(raw)
        if len(t) < 70 or junk.search(t):
            continue
        out.append(t)
        total += len(t)
        if total >= want:
            break
    return " ".join(out)


def enrich(items, want=900):
    """Fetch article bodies in parallel so print stories have real text."""
    def one(it):
        it["text"] = it["desc"]
        if "news.google.com" in it["link"]:
            return
        try:
            t = article_text(it["link"], want)
        except Exception as e:  # noqa: BLE001
            log(f"article fetch failed: {it['link'][:70]} ({e})")
            return
        if len(t) > len(it["text"]):
            it["text"] = t
    with ThreadPoolExecutor(8) as ex:
        list(ex.map(one, items))
    return items


def best(items, n):
    """Keep the n items with the most readable text, in their original (newest-first) order."""
    ranked = sorted(enumerate(items), key=lambda p: (len(p[1].get("text", "")) < 150, p[0]))
    return [it for _, it in sorted(ranked[:n])]


def collect(feed_list, limit, per_feed=None, max_age_hours=None):
    """Merge feeds, dedupe on title, newest first (round-robin so one source can't hog)."""
    now = datetime.now(timezone.utc)
    buckets = []
    for source, url in feed_list:
        try:
            items = parse_feed(url, source)
        except Exception as e:  # noqa: BLE001
            log(f"feed failed: {e}")
            continue
        if max_age_hours:
            items = [i for i in items
                     if i["when"] is None or (now - i["when"]).total_seconds() < max_age_hours * 3600]
        items.sort(key=lambda i: i["when"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        buckets.append(items[:per_feed] if per_feed else items)
    out, seen = [], SHARED_SEEN
    while buckets and len(out) < limit:
        progressed = False
        for b in buckets:
            while b:
                it = b.pop(0)
                key = re.sub(r"\W+", "", it["title"].lower())[:60]
                if key in seen or BLOCK.search(it["title"]):
                    continue
                seen.add(key)
                out.append(it)
                progressed = True
                break
            if len(out) >= limit:
                break
        if not progressed:
            break
    return out


def ago(when):
    if not when:
        return ""
    secs = (datetime.now(timezone.utc) - when).total_seconds()
    if secs < 3600:
        return f"{max(1, int(secs // 60))}m ago"
    if secs < 86400:
        return f"{int(secs // 3600)}h ago"
    return f"{int(secs // 86400)}d ago"


def story_list(items, lede=False, desc_len=170):
    if not items:
        return '<p class="muted">Nothing fit to print from this source right now.</p>'
    out = []
    for n, it in enumerate(items):
        first = lede and n == 0
        cls = "story lede" if first else "story"
        if PRINT:
            d = clip(it.get("text") or it["desc"], (900 if first else 430) if desc_len else 0)
        else:
            d = clip(it["desc"], 260 if first else desc_len) if desc_len else ""
        desc = f"<p>{esc(d)}</p>" if re.search(r"\w{3}", d) else ""
        meta = " &middot; ".join(x for x in (esc(it["source"]), esc(ago(it["when"]))) if x)
        out.append(f'<article class="{cls}"><h3><a href="{esc(it["link"])}">{esc(it["title"])}</a></h3>'
                   f'{desc}<span class="meta">{meta}</span></article>')
    return "\n".join(out)


# ------------------------------------------------------------- weather -----
def weather_section():
    parts = {"lead": "", "forecast": "", "alerts": "", "tropics": "", "now": ""}

    # Space City Weather: newest post, best-effort
    try:
        posts = parse_rss(fetch(FEEDS["scw"]), "Space City Weather")
        p = posts[0]
        text = strip_html(p["full"] or p["desc"])
        paras = [x.strip() for x in re.split(r"\n{2,}", text) if len(x.strip()) > 60]
        body = "".join(f"<p>{esc(clip(x, 800 if PRINT else 520))}</p>" for x in paras[: 4 if PRINT else 3])
        parts["lead"] = (
            f'<h2 class="hed"><a href="{esc(p["link"])}">{esc(p["title"])}</a></h2>'
            f'<p class="byline">Space City Weather &middot; {esc(ago(p["when"]))}</p>{body}'
            f'<p><a class="more" href="{esc(p["link"])}">Read the full forecast &rarr;</a></p>')
    except Exception as e:  # noqa: BLE001
        log(f"scw failed: {e}")
        parts["lead"] = ('<h2 class="hed">Forecast desk unavailable</h2>'
                         '<p><a class="more" href="https://spacecityweather.com">Go to Space City Weather &rarr;</a></p>')

    # NWS 7-day
    headline_now = ""
    try:
        d = get_json(f"https://api.weather.gov/gridpoints/{HOUSTON['nws_grid']}/forecast")
        periods = d["properties"]["periods"]
        days = [p for p in periods if p["isDaytime"]][:5]
        by_name = {p["name"]: p for p in periods}
        cells = []
        for p in days:
            idx = periods.index(p)
            night = periods[idx + 1] if idx + 1 < len(periods) and not periods[idx + 1]["isDaytime"] else None
            lo = f'<span class="lo">{night["temperature"]}&deg;</span>' if night else ""
            pop = (p.get("probabilityOfPrecipitation") or {}).get("value")
            rain = f'<span class="pop">{pop}% rain</span>' if pop else ""
            cells.append(f'<div class="day"><b>{esc(p["name"][:3])}</b>'
                         f'<span class="hi">{p["temperature"]}&deg;</span>{lo}'
                         f'<span class="sf">{esc(p["shortForecast"])}</span>{rain}</div>')
        parts["forecast"] = '<div class="days">' + "".join(cells) + "</div>"
        first = periods[0]
        headline_now = f'{first["temperature"]}&deg;F &middot; {esc(first["shortForecast"])}'
        parts["now"] = (f'<p class="now"><b>{esc(first["name"])}:</b> '
                        f'{esc(clip(first["detailedForecast"], 240))}</p>')
    except Exception as e:  # noqa: BLE001
        log(f"nws forecast failed: {e}")
        parts["forecast"] = '<p class="muted">NWS forecast unavailable.</p>'

    # NWS alerts
    try:
        d = get_json(f"https://api.weather.gov/alerts/active?point={HOUSTON['lat']},{HOUSTON['lon']}")
        feats = d.get("features", [])
        if feats:
            items = "".join(
                f'<li><b>{esc(f["properties"]["event"])}</b> &mdash; '
                f'{esc(clip(f["properties"].get("headline") or "", 160))}</li>' for f in feats[:4])
            parts["alerts"] = f'<div class="alert"><h4>Weather alerts</h4><ul>{items}</ul></div>'
        else:
            parts["alerts"] = '<p class="calm">No active NWS watches or warnings for Houston.</p>'
    except Exception as e:  # noqa: BLE001
        log(f"nws alerts failed: {e}")

    # NHC
    try:
        items = parse_rss(fetch(FEEDS["nhc"]), "NHC")
        storms = [i for i in items if not re.search(r"graphical|outlook|no tropical", i["title"], re.I)]
        if storms:
            lis = "".join(f'<li><a href="{esc(s["link"])}">{esc(s["title"])}</a></li>' for s in storms[:3])
            parts["tropics"] = f'<div class="alert"><h4>In the tropics</h4><ul>{lis}</ul></div>'
        else:
            parts["tropics"] = ('<p class="calm">Tropics: no active Atlantic cyclones per the '
                                '<a href="https://www.nhc.noaa.gov/">National Hurricane Center</a>.</p>')
    except Exception as e:  # noqa: BLE001
        log(f"nhc failed: {e}")
    return parts, headline_now


# -------------------------------------------------------------- sports -----
def stat(entry, key):
    for s in entry.get("stats", []):
        if s.get("type") == key or s.get("name") == key:
            return s.get("displayValue", s.get("value"))
    return None


def fnum(v, default=0.0):
    try:
        return float(v)
    except Exception:  # noqa: BLE001
        return default


def score_of(comp):
    s = comp.get("score")
    if isinstance(s, dict):
        return s.get("displayValue")
    return s


def parse_events(events, team_id):
    out = []
    for e in events:
        c = e["competitions"][0]
        me = next((x for x in c["competitors"] if x["team"]["id"] == team_id), None)
        opp = next((x for x in c["competitors"] if x["team"]["id"] != team_id), None)
        if not me or not opp:
            continue
        st = c["status"]["type"]
        out.append({
            "date": datetime.fromisoformat(e["date"].replace("Z", "+00:00")),
            "done": bool(st.get("completed")),
            "opp": opp["team"]["displayName"],
            "ha": me["homeAway"],
            "me": score_of(me), "them": score_of(opp),
            "win": me.get("winner"),
            "venue": (c.get("venue") or {}).get("fullName", ""),
            "comp": (e.get("league") or {}).get("name") or e.get("seasonType", {}).get("name", ""),
            "id": e["id"],
        })
    out.sort(key=lambda x: x["date"])
    return out


def when_ct(dt):
    d = dt.astimezone(CT)
    return d.strftime("%a %b %-d, %-I:%M %p CT").replace(":00 ", " ")


def result_html(ev, team):
    r = "W" if ev["win"] else ("L" if ev["win"] is False else "D")
    rcls = {"W": "w", "L": "l", "D": "d"}[r]
    at = "at" if ev["ha"] == "away" else "vs."
    return (f'<div class="fx"><span class="tag">Last time out</span>'
            f'<b class="res {rcls}">{r} {esc(ev["me"])}&ndash;{esc(ev["them"])}</b> '
            f'{at} {esc(ev["opp"])}<span class="meta">{esc(ev["date"].astimezone(CT).strftime("%b %-d"))}</span></div>')


def next_html(evs, team, count=3):
    if not evs:
        return ""
    rows = []
    for n, ev in enumerate(evs[:count]):
        at = "at" if ev["ha"] == "away" else "vs."
        label = "Up next" if n == 0 else "Then"
        comp = f' <span class="meta">{esc(ev["comp"])}</span>' if ev.get("comp") else ""
        rows.append(f'<div class="fx"><span class="tag">{label}</span> {at} <b>{esc(ev["opp"])}</b>'
                    f'<span class="meta">{esc(when_ct(ev["date"]))}{(" &middot; " + esc(ev["venue"])) if ev["venue"] else ""}</span>{comp}</div>')
    return "".join(rows)


def window(rows, hi_idx, top):
    keep = set(range(min(top, len(rows))))
    if hi_idx is not None:
        keep |= {i for i in (hi_idx - 1, hi_idx, hi_idx + 1) if 0 <= i < len(rows)}
    out, prev = [], -1
    for i in sorted(keep):
        if i - prev > 1:
            out.append(None)
        out.append((i, rows[i]))
        prev = i
    return out


def table_html(head, body_rows, colspan):
    th = "".join(f"<th>{h}</th>" for h in head)
    trs = []
    for r in body_rows:
        if r is None:
            trs.append(f'<tr class="gap"><td colspan="{colspan}">&hellip;</td></tr>')
        else:
            cls = ' class="me"' if r[0] else ""
            trs.append(f"<tr{cls}>" + "".join(f"<td>{c}</td>" for c in r[1]) + "</tr>")
    return f'<table class="tbl"><thead><tr>{th}</tr></thead><tbody>{"".join(trs)}</tbody></table>'


def aggies_section():
    out = {"sched": "", "sec": "", "rank": ""}
    ranks = {}
    try:
        d = get_json(f"{ESPN}/site/v2/sports/football/college-football/rankings")
        for rk in d["rankings"]:
            if rk["name"].startswith("AP"):
                for x in rk["ranks"]:
                    ranks[x["team"]["id"]] = x["current"]
    except Exception as e:  # noqa: BLE001
        log(f"rankings failed: {e}")

    try:
        d = get_json(f"{ESPN}/site/v2/sports/football/college-football/teams/{AGGIES_ID}/schedule?seasontype=2")
        evs = parse_events(d["events"], AGGIES_ID)
        done = [e for e in evs if e["done"]]
        todo = [e for e in evs if not e["done"]]
        out["sched"] = (result_html(done[-1], "Aggies") if done else "") + next_html(todo, "Aggies", 3)
    except Exception as e:  # noqa: BLE001
        log(f"aggies schedule failed: {e}")
        out["sched"] = '<p class="muted">Schedule unavailable.</p>'

    try:
        d = get_json(f"{ESPN}/v2/sports/football/college-football/standings?group={SEC_GROUP}")
        ents = d["standings"]["entries"]
        ents.sort(key=lambda e: (-fnum(stat(e, "vsconf_leaguewinpercent")),
                                 -fnum(stat(e, "winpercent") or 0),
                                 -fnum(stat(e, "vsconf_wins"))))
        rows, hi = [], None
        for i, e in enumerate(ents):
            t = e["team"]
            is_me = t["id"] == AGGIES_ID
            if is_me:
                hi = i
            rk = ranks.get(t["id"])
            name = esc(t.get("shortDisplayName") or t["displayName"])
            if rk:
                name = f'<sup class="rk">{rk}</sup> {name}'
            rows.append((is_me, [i + 1, name, esc(stat(e, "vsconf")), esc(stat(e, "total")),
                                 esc(stat(e, "streak"))]))
        out["sec"] = table_html(["#", "SEC team", "Conf", "All", "Strk"], [
            r if r is None else (r[1][0], r[1][1]) for r in window(rows, hi, 8)], 5)
        if hi is not None and ranks.get(AGGIES_ID):
            out["rank"] = f'No. {ranks[AGGIES_ID]} in the AP poll'
        elif hi is not None:
            out["rank"] = "Unranked in the AP poll"
    except Exception as e:  # noqa: BLE001
        log(f"sec standings failed: {e}")
        out["sec"] = '<p class="muted">Standings unavailable.</p>'
    return out


def liverpool_section():
    out = {"sched": "", "epl": "", "ucl": ""}
    try:
        past = get_json(f"{ESPN}/site/v2/sports/soccer/all/teams/{LIVERPOOL_ID}/schedule")
        evs = parse_events(past["events"], LIVERPOOL_ID)
        done = [e for e in evs if e["done"]]
        upcoming = []
        for lg, name in (("eng.1", "Premier League"), ("uefa.champions", "Champions League"),
                         ("eng.league_cup", "League Cup"), ("eng.fa", "FA Cup")):
            try:
                f = get_json(f"{ESPN}/site/v2/sports/soccer/{lg}/teams/{LIVERPOOL_ID}/schedule?fixture=true")
                for e in parse_events(f["events"], LIVERPOOL_ID):
                    e["comp"] = name
                    upcoming.append(e)
            except Exception as e:  # noqa: BLE001
                log(f"fixtures {lg}: {e}")
        now = datetime.now(timezone.utc)
        upcoming = sorted((e for e in upcoming if not e["done"] and e["date"] > now), key=lambda e: e["date"])
        out["sched"] = (result_html(done[-1], "Liverpool") if done else "") + next_html(upcoming, "Liverpool", 3)
    except Exception as e:  # noqa: BLE001
        log(f"liverpool schedule failed: {e}")
        out["sched"] = '<p class="muted">Fixtures unavailable.</p>'

    def league_table(url, head_label, top, pick_children):
        d = get_json(url)
        node = d["children"][0] if pick_children else d
        ents = node["standings"]["entries"]
        ents.sort(key=lambda e: fnum(stat(e, "rank"), 99))
        rows, hi = [], None
        for i, e in enumerate(ents):
            is_me = e["team"]["id"] == LIVERPOOL_ID
            if is_me:
                hi = i
            rows.append((is_me, [esc(stat(e, "rank")), esc(e["team"].get("shortDisplayName") or e["team"]["displayName"]),
                                 esc(stat(e, "gamesPlayed")), esc(stat(e, "overall")),
                                 esc(stat(e, "pointDifferential")), f'<b>{esc(stat(e, "points"))}</b>']))
        return table_html(["#", head_label, "P", "W-D-L", "GD", "Pts"],
                          [r if r is None else (r[1][0], r[1][1]) for r in window(rows, hi, top)], 6)

    try:
        out["epl"] = league_table(f"{ESPN}/v2/sports/soccer/eng.1/standings", "Premier League", 6, True)
    except Exception as e:  # noqa: BLE001
        log(f"epl standings failed: {e}")
        out["epl"] = '<p class="muted">Table unavailable.</p>'
    try:
        out["ucl"] = league_table(f"{ESPN}/v2/sports/soccer/uefa.champions/standings", "Champions League", 8, True)
    except Exception as e:  # noqa: BLE001
        log(f"ucl standings failed: {e}")
        out["ucl"] = '<p class="muted">Table unavailable.</p>'
    return out


# ---------------------------------------------------------------- page -----
CSS = """
:root{--paper:#f3ecdc;--paper2:#ebe2cc;--ink:#1a1712;--muted:#6b6354;--rule:#1a1712;--hair:#bdb298;
--accent:#9b1c1c;--aggie:#500000;--lfc:#c8102e;--sky:#1d4e7a;--font:"Libre Baskerville",Georgia,"Times New Roman",serif;
--head:"Playfair Display",Georgia,"Times New Roman",serif;--sans:system-ui,-apple-system,"Segoe UI",Helvetica,Arial,sans-serif}
@media(prefers-color-scheme:dark){:root{--paper:#17150f;--paper2:#201d15;--ink:#ece4d0;--muted:#a39b86;--rule:#ece4d0;--hair:#4a4536;
--accent:#e0645a;--aggie:#e58b8b;--lfc:#ff5a6e;--sky:#7fb3e0}}
*{box-sizing:border-box}
body{margin:0;background:var(--paper2);color:var(--ink);font:15px/1.5 var(--font)}
a{color:inherit;text-decoration:none}a:hover{text-decoration:underline}
.sheet{max-width:1180px;margin:0 auto;padding:18px 24px 28px;background:var(--paper);
box-shadow:0 0 0 1px var(--hair),0 10px 40px rgba(0,0,0,.18)}
.topline{display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;font:600 11px var(--sans);
letter-spacing:.12em;text-transform:uppercase;border-bottom:1px solid var(--rule);padding-bottom:6px}
.mast{text-align:center;padding:14px 0 6px;border-bottom:4px double var(--rule)}
.mast h1{font:900 clamp(40px,8.5vw,92px)/1 "UnifrakturCook","Playfair Display",Georgia,serif;margin:0;letter-spacing:.01em}
.mast .tag{font:italic 14px var(--font);color:var(--muted);margin-top:6px}
.dateline{display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;font:600 12px var(--sans);
letter-spacing:.08em;text-transform:uppercase;border-bottom:1px solid var(--rule);padding:7px 0}
.grid{display:grid;grid-template-columns:1.55fr 1fr 1fr;gap:0;margin-top:16px}
.col{padding:0 18px;border-left:1px solid var(--hair)}.col:first-child{padding-left:0;border-left:0}.col:last-child{padding-right:0}
.sec{margin:0 0 22px}
.kicker{font:800 11px var(--sans);letter-spacing:.16em;text-transform:uppercase;color:var(--accent);
border-top:3px solid currentColor;padding-top:5px;margin:0 0 8px;display:flex;justify-content:space-between;gap:8px}
.kicker span{font-weight:600;letter-spacing:.06em;color:var(--muted);text-transform:none}
.kicker.sky{color:var(--sky)}.kicker.aggie{color:var(--aggie)}.kicker.lfc{color:var(--lfc)}
.hed{font:900 clamp(26px,3.4vw,38px)/1.08 var(--head);margin:4px 0 6px}
.byline{font:600 11px var(--sans);letter-spacing:.08em;text-transform:uppercase;color:var(--muted);margin:0 0 10px}
p{margin:0 0 10px}.more{font:700 12px var(--sans);letter-spacing:.06em;text-transform:uppercase;color:var(--sky)}
.muted{color:var(--muted);font-style:italic}
.story{padding:9px 0;border-top:1px solid var(--hair)}.story:first-child{border-top:0;padding-top:0}
.story h3{font:700 16px/1.25 var(--head);margin:0 0 3px}
.story.lede h3{font-size:21px}
.story p{font-size:13px;color:var(--muted);margin:2px 0 3px}
.meta{display:block;font:11px var(--sans);color:var(--muted);letter-spacing:.03em}
.days{display:grid;grid-template-columns:repeat(5,1fr);border:1px solid var(--rule);margin:10px 0}
.day{padding:7px 4px;text-align:center;border-left:1px solid var(--hair);font:12px var(--sans)}.day:first-child{border-left:0}
.day b{display:block;text-transform:uppercase;letter-spacing:.1em;font-size:10px}
.hi{font:800 22px var(--head);display:block}.lo{color:var(--muted);font:13px var(--sans);display:block}
.sf{display:block;font-size:10.5px;line-height:1.25;color:var(--muted);margin-top:3px}.pop{display:block;color:var(--sky);font-weight:700;font-size:10.5px}
.now{font-size:13px;border-left:3px solid var(--sky);padding-left:10px}
.alert{border:1px solid var(--accent);background:rgba(155,28,28,.07);padding:8px 12px;margin:10px 0;font-size:13px}
.alert h4{margin:0 0 4px;font:800 11px var(--sans);letter-spacing:.14em;text-transform:uppercase;color:var(--accent)}
.alert ul{margin:0;padding-left:18px}.calm{font-size:12.5px;color:var(--muted);margin:6px 0}.calm a{text-decoration:underline}
.fx{font-size:13.5px;padding:6px 0;border-top:1px solid var(--hair)}.fx:first-of-type{border-top:0}
.fx .tag{font:800 10px var(--sans);letter-spacing:.14em;text-transform:uppercase;color:var(--muted);display:block}
.res{font-family:var(--sans)}.res.w{color:#1f7a3a}.res.l{color:var(--accent)}.res.d{color:var(--muted)}
.tbl{width:100%;border-collapse:collapse;font:12px var(--sans);margin:4px 0 8px}
.tbl th{white-space:nowrap;text-align:left;font-size:10px;letter-spacing:.08em;text-transform:uppercase;border-bottom:2px solid var(--rule);padding:3px 4px}
.tbl td{padding:3px 4px;border-bottom:1px solid var(--hair)}.tbl td:first-child{width:24px;color:var(--muted)}
.tbl tr.me td{font-weight:800;background:rgba(155,28,28,.1)}.tbl tr.gap td{text-align:center;color:var(--muted)}
.aggie-tbl tr.me td{background:rgba(80,0,0,.12)}.rk{font-size:9px;color:var(--accent);font-weight:700}
.sub{font:800 11px var(--sans);letter-spacing:.1em;text-transform:uppercase;margin:12px 0 2px}
.foot{margin-top:8px;border-top:4px double var(--rule);padding-top:8px;font:11px var(--sans);color:var(--muted);
display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap}
@media(max-width:900px){.grid{grid-template-columns:1fr}.col{padding:0;border-left:0}.sheet{padding:12px 14px}}
@media print{body{background:#fff}.sheet{box-shadow:none;max-width:none}}
.toolbar{display:flex;gap:14px;align-items:center;justify-content:flex-end;max-width:1180px;margin:0 auto;padding:8px 24px;font:600 12px var(--sans)}
.toolbar span{margin-right:auto;letter-spacing:.1em;text-transform:uppercase;color:var(--muted)}
.toolbar a{color:var(--sky);text-decoration:underline}
.toolbar button{font:700 12px var(--sans);background:var(--ink);color:var(--paper);border:0;padding:7px 14px;cursor:pointer;border-radius:3px}
/* ---- web extras ---- */
.tabs{display:flex;gap:6px;flex-wrap:wrap;margin:10px 0 0}
.tabs button{font:700 11px var(--sans);letter-spacing:.08em;text-transform:uppercase;background:transparent;color:var(--ink);
border:1px solid var(--rule);padding:6px 12px;cursor:pointer;border-radius:2px}
.tabs button[aria-pressed=true]{background:var(--ink);color:var(--paper)}
.live{font-variant-numeric:tabular-nums}
/* ---- print edition: two US-Letter pages (front + sports), greyscale ---- */
body.print{--paper:#fff;--paper2:#d6d6d6;--ink:#111;--muted:#4a4a4a;--rule:#111;--hair:#9a9a9a;--accent:#111;--aggie:#111;--lfc:#111;--sky:#111;
background:var(--paper2);color:var(--ink);font-size:calc(11.5px*var(--s,1));line-height:1.38}
body.print .toolbar{max-width:8.5in}
body.print .page{width:8.5in;height:11in;margin:14px auto;background:#fff;overflow:hidden;box-shadow:0 0 0 1px var(--hair),0 6px 24px rgba(0,0,0,.25)}
body.print .sheet{max-width:none;width:100%;margin:0 auto;padding:.3in .35in;box-shadow:none;background:#fff}
body.print .mast{padding:6px 0 4px}body.print .mast h1{font-size:calc(62px*var(--s,1))}body.print .mast.mini h1{font-size:calc(34px*var(--s,1))}
body.print .mast .tag{font-size:calc(11px*var(--s,1));margin-top:2px}
body.print .grid{margin-top:10px;grid-template-columns:1.25fr 1fr 1fr}
body.print .col{padding:0 11px;border-left:1px solid var(--hair)}body.print .col:first-child{padding-left:0;border-left:0}body.print .col:last-child{padding-right:0}
body.print .sec{margin-bottom:12px}body.print .kicker{font-size:calc(9px*var(--s,1));margin-bottom:6px;padding-top:3px;flex-wrap:wrap}
body.print .hed{font-size:calc(25px*var(--s,1));margin:2px 0 4px}body.print .byline{font-size:calc(8.5px*var(--s,1));margin-bottom:6px}
body.print .lead p{margin-bottom:6px;text-align:justify;hyphens:auto}
body.print .more,body.print .toolbar+.sheet .more{display:none}
body.print .story{padding:6px 0}body.print .story h3{font-size:calc(14px*var(--s,1));line-height:1.2}body.print .story.lede h3{font-size:calc(18px*var(--s,1))}
body.print .story p{font-size:calc(11px*var(--s,1));color:var(--ink);text-align:justify;hyphens:auto;margin:3px 0 2px}
body.print .meta{font-size:calc(8.5px*var(--s,1))}body.print .now{font-size:calc(11px*var(--s,1))}
body.print .days{margin:8px 0}body.print .day{padding:5px 2px;font-size:calc(10px*var(--s,1))}body.print .hi{font-size:calc(17px*var(--s,1))}body.print .sf{font-size:calc(8.5px*var(--s,1))}
body.print .calm{font-size:calc(10px*var(--s,1))}body.print .alert{background:#eee;border-color:#111;font-size:calc(10.5px*var(--s,1))}
body.print .tbl{font-size:calc(10px*var(--s,1))}body.print .tbl th,body.print .tbl td{padding:2px 3px}
body.print .tbl tr.me td{background:#d9d9d9}body.print .aggie-tbl tr.me td{background:#d9d9d9}
body.print .res.w,body.print .res.l,body.print .res.d{color:#111}
body.print .fx{font-size:calc(11px*var(--s,1));padding:4px 0}body.print .sub{font-size:calc(9px*var(--s,1));margin-top:8px}
body.print .dateline{font-size:calc(9.5px*var(--s,1));padding:4px 0}body.print .topline{font-size:calc(8.5px*var(--s,1))}body.print .foot{font-size:calc(8.5px*var(--s,1))}
body.print .xw{display:grid;grid-template-columns:repeat(15,.39in);grid-auto-rows:.39in;width:max-content;margin:.12in auto .1in;border:2px solid #111}
body.print .xw div{border:1px solid #111;position:relative;background:#fff}
body.print .xw div.b{background:#222}
body.print .xw i{position:absolute;top:1px;left:2px;font:700 9px/1 var(--sans);font-style:normal}
body.print .clues{display:grid;grid-template-columns:1fr 1fr;gap:.25in;font-size:11px;line-height:1.3}
body.print .clues h4{margin:0 0 3px;font:800 10px var(--sans);letter-spacing:.14em;text-transform:uppercase;border-bottom:2px solid #111}
body.print .clues ol{list-style:none;margin:0;padding:0;columns:1}
body.print .clues li{margin:0 0 2px}body.print .clues li b{font-family:var(--sans)}
body.print .clues li span{color:var(--muted);font-size:9px}
body.print .yest{position:absolute;right:.35in;top:.5in;display:flex;align-items:flex-end;gap:5px;font:7px/1.2 var(--sans);color:var(--muted)}
body.print .yest span{letter-spacing:.08em;text-transform:uppercase;text-align:right;width:.6in}
body.print .xwmini{display:grid;grid-template-columns:repeat(15,4px);grid-auto-rows:4px;margin-left:auto;width:max-content;border:1px solid #777}
body.print .xwmini div{font:3.2px/4px var(--sans);text-align:center;color:#111}body.print .xwmini div.b{background:#555}
body.print .page{position:relative}
@page{size:letter;margin:0}
@media print{
  .toolbar{display:none}
  html,body,body.print{background:#fff;-webkit-print-color-adjust:exact;print-color-adjust:exact}
  body.print .page{margin:0;box-shadow:none;break-after:page;page-break-after:always}
  body.print .page:last-of-type{break-after:auto;page-break-after:auto}
  body.screen .sheet{box-shadow:none}.tabs{display:none}
  .story,.fx,.tbl,.alert{break-inside:avoid}
}
"""


def build():
    SHARED_SEEN.clear()
    now = datetime.now(CT)
    wx, now_line = weather_section()

    log("fetching news...")
    P = PRINT
    n = (lambda web, prt: prt if P else web)
    # print pulls extra candidates, then keeps the ones whose article text is actually readable
    houston = collect(FEEDS["houston"], n(7, 12), per_feed=8, max_age_hours=72)
    aggie_news = collect(FEEDS["aggies"], n(6, 10), per_feed=8, max_age_hours=96)
    sec_news = collect(FEEDS["sec"], n(5, 9), per_feed=8, max_age_hours=60)
    lfc_news = collect(FEEDS["lfc"], n(6, 10), per_feed=8, max_age_hours=96)
    fb_news = collect(FEEDS["football"], n(6, 8), per_feed=6, max_age_hours=72)
    nat = collect(FEEDS["national"], n(5, 8), max_age_hours=48)
    world = collect(FEEDS["world"], n(5, 8), max_age_hours=48)
    if P:
        log("reading articles for the print edition...")
        for grp in (houston, aggie_news, sec_news, lfc_news, fb_news, nat, world):
            enrich(grp)
        houston, aggie_news, sec_news = best(houston, 4), best(aggie_news, 3), best(sec_news, 3)
        lfc_news, fb_news = best(lfc_news, 3), best(fb_news, 2)
        nat, world = best(nat, 3), best(world, 2)

    log("fetching sports data...")
    ag = aggies_section()
    lv = liverpool_section()

    edition = now.strftime("%A, %B %-d, %Y")
    updated = now.strftime("%-I:%M %p CT")
    ag_rank = f"<span>{esc(ag['rank'])}</span>" if ag["rank"] else ""
    nat_world = story_list(nat[: n(4, 3)] + world[: n(4, 2)], desc_len=140)

    weather = (f'<section class="sec" data-topic="weather"><div class="kicker sky">Weather <span>via Space City Weather &amp; NWS</span></div>'
               f'<div class="lead">{wx["lead"]}</div>{wx["alerts"]}{wx["forecast"]}{wx["now"]}{wx["tropics"]}</section>')
    houston_sec = f'<section class="sec" data-topic="news"><div class="kicker">Around Houston</div>{story_list(houston, lede=True)}</section>'
    world_sec = f'<section class="sec" data-topic="news"><div class="kicker">The Nation &amp; the World</div>{nat_world}</section>'
    aggie_top = (f'<section class="sec" data-topic="aggies"><div class="kicker aggie">Gig &rsquo;Em &middot; Texas A&amp;M Football {ag_rank}</div>'
                 f'{ag["sched"]}<div class="sub">SEC Standings</div><div class="aggie-tbl">{ag["sec"]}</div></section>')
    aggie_rep = f'<section class="sec" data-topic="aggies"><div class="kicker aggie">Aggie Report</div>{story_list(aggie_news, lede=True)}</section>'
    sec_rep = f'<section class="sec" data-topic="aggies"><div class="kicker aggie">Around the SEC &amp; College Football</div>{story_list(sec_news, desc_len=0 if not P else 1)}</section>'
    lfc_top = (f'<section class="sec" data-topic="lfc"><div class="kicker lfc">You&rsquo;ll Never Walk Alone &middot; Liverpool FC</div>{lv["sched"]}'
               f'<div class="sub">Premier League</div>{lv["epl"]}<div class="sub">Champions League &middot; League Phase</div>{lv["ucl"]}</section>')
    lfc_rep = f'<section class="sec" data-topic="lfc"><div class="kicker lfc">Anfield Report</div>{story_list(lfc_news, lede=True)}</section>'
    fb_rep = f'<section class="sec" data-topic="lfc"><div class="kicker lfc">Premier League &amp; Europe</div>{story_list(fb_news, desc_len=0 if not P else 1)}</section>'

    head = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>The H-Town Observer &mdash; {esc(edition)}</title>
<meta name="description" content="A daily front page for Houston weather, Texas A&amp;M, the SEC, Liverpool and the world.">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Libre+Baskerville:wght@400;700&amp;family=Playfair+Display:wght@700;900&amp;family=UnifrakturCook:wght@700&amp;display=swap" rel="stylesheet">
<style>{CSS}</style></head>"""
    foot = ('<footer class="foot"><span>Compiled automatically each morning from Space City Weather, NWS, NHC, ESPN, The Guardian, BBC, NYT, '
            'Houston Public Media, KPRC and Google News.</span><span>Headlines link to the original publishers.</span></footer>')

    if P:
        fit = """<script>
(function(){
  var MAX=1050;
  function over(s){return s.scrollHeight>MAX}
  function fit(s){
    if(s._orig===undefined)s._orig=s.innerHTML;else s.innerHTML=s._orig;
    var z=1;s.style.setProperty('--s',z);
    while(over(s)&&z>0.88){z=Math.round((z-0.02)*100)/100;s.style.setProperty('--s',z);}
    var guard=0;
    while(over(s)&&guard++<40){
      var worst=null,wb=-1;
      s.querySelectorAll('.col').forEach(function(c){var l=c.lastElementChild;var b=l?l.getBoundingClientRect().bottom:0;if(b>wb){wb=b;worst=c}});
      var st=worst.querySelectorAll('.story'),rm=null;
      for(var i=st.length-1;i>=0;i--){var pv=st[i].previousElementSibling;if(pv&&pv.classList.contains('story')){rm=st[i];break}}
      if(!rm)break;rm.remove();
    }
  }
  function all(){document.querySelectorAll('.sheet:not(.nofit)').forEach(fit)}
  window.addEventListener('load',all);
  if(document.fonts&&document.fonts.ready)document.fonts.ready.then(all);
  window.addEventListener('beforeprint',all);
})();
</script>"""
        toolbar = ('<nav class="toolbar"><span>The H-Town Observer &middot; print edition (3 pages, greyscale)</span>'
                   '<a href="index.html">&larr; Web edition</a><button onclick="window.print()">Print this edition</button></nav>')
        p1 = f"""<div class="page"><div class="sheet">
<div class="topline"><span>Houston, Texas</span><span>Weather &middot; Aggies &middot; The Reds &middot; The World</span><span>Page 1 of 3 &middot; Sports &amp; puzzle inside</span></div>
<header class="mast"><h1>The H-Town Observer</h1>
<div class="tag">&ldquo;All the weather, all the Aggies, all the Reds &mdash; fit to print.&rdquo;</div></header>
<div class="dateline"><span>{esc(edition)}</span><span>{now_line}</span><span>Updated {esc(updated)}</span></div>
<div class="grid"><div class="col">{weather}</div><div class="col">{houston_sec}</div><div class="col">{world_sec}</div></div>
{foot}</div></div>"""
        p2 = f"""<div class="page"><div class="sheet">
<div class="topline"><span>The H-Town Observer</span><span>The Sports Page</span><span>Page 2 of 3</span></div>
<header class="mast mini"><h1>Sports &amp; Scoreboard</h1>
<div class="tag">Texas A&amp;M &middot; the SEC &middot; Liverpool &middot; the Premier League &amp; Europe</div></header>
<div class="dateline"><span>{esc(edition)}</span><span>Gig &rsquo;Em &amp; YNWA</span><span>Updated {esc(updated)}</span></div>
<div class="grid"><div class="col">{aggie_top}{aggie_rep}</div><div class="col">{lfc_top}{fb_rep}</div><div class="col">{lfc_rep}{sec_rep}</div></div>
{foot}</div></div>"""
        xw, yesterday, _ = crossword_render(now.date())
        p3 = f"""<div class="page"><div class="sheet nofit">
<div class="topline"><span>The H-Town Observer</span><span>The Puzzle Page</span><span>Page 3 of 3</span></div>
<header class="mast mini"><h1>The Crossword</h1>
<div class="tag">Medium &middot; everyday words, dictionary-style clues</div></header>
<div class="dateline"><span>{esc(edition)}</span><span>Pens at the ready</span><span>Answers: tomorrow&rsquo;s paper</span></div>
{xw}
<div class="yest"><span>Yesterday&rsquo;s solution</span>{yesterday}</div>
</div></div>"""
        return f'{head}<body class="print">{toolbar}{p1}{p2}{p3}{fit}</body></html>'

    toolbar = ('<nav class="toolbar"><span>The H-Town Observer</span><a href="print.html">Print edition</a>'
               '<button onclick="window.print()">Print</button></nav>')
    tabs = ('<div class="tabs" role="group" aria-label="Sections">'
            '<button data-view="all" aria-pressed="true">All</button><button data-view="weather">Weather</button>'
            '<button data-view="news">Houston &amp; World</button><button data-view="aggies">Aggies &amp; SEC</button>'
            '<button data-view="lfc">Liverpool &amp; Europe</button></div>')
    js = """<script>
(function(){
  var tabs=document.querySelectorAll('.tabs button'),grid=document.querySelector('.grid');
  function show(v){
    tabs.forEach(function(b){b.setAttribute('aria-pressed',b.dataset.view===v)});
    document.querySelectorAll('.sec').forEach(function(s){s.hidden=!(v==='all'||s.dataset.topic===v)});
    var vis=0;document.querySelectorAll('.col').forEach(function(c){var any=c.querySelector('.sec:not([hidden])');c.hidden=!any;if(any)vis++});
    grid.style.gridTemplateColumns=v==='all'?'':'repeat('+Math.max(1,vis)+',1fr)';
    try{localStorage.setItem('observerView',v)}catch(e){}
  }
  tabs.forEach(function(b){b.addEventListener('click',function(){show(b.dataset.view)})});
  try{var v=localStorage.getItem('observerView');if(v)show(v)}catch(e){}
  // live temperature straight from the National Weather Service
  var el=document.getElementById('nowline');
  fetch('https://api.weather.gov/gridpoints/HGX/65,97/forecast/hourly').then(function(r){return r.json()}).then(function(d){
    var p=d.properties.periods[0];el.innerHTML=p.temperature+'&deg;F &middot; '+p.shortForecast+' <small>(live)</small>';
  }).catch(function(){});
})();
</script>"""
    return f"""{head}
<body class="screen">{toolbar}<div class="sheet">
<div class="topline"><span>Houston, Texas</span><span>Weather &middot; Aggies &middot; The Reds &middot; The World</span><span>Edition no. {now.timetuple().tm_yday}</span></div>
<header class="mast"><h1>The H-Town Observer</h1>
<div class="tag">&ldquo;All the weather, all the Aggies, all the Reds &mdash; fit to print.&rdquo;</div></header>
<div class="dateline"><span>{esc(edition)}</span><span class="live" id="nowline">{now_line}</span><span>Updated {esc(updated)}</span></div>
{tabs}
<div class="grid">
<div class="col">{weather}{houston_sec}{world_sec}</div>
<div class="col">{aggie_top}{aggie_rep}{sec_rep}</div>
<div class="col">{lfc_top}{lfc_rep}{fb_rep}</div>
</div>
{foot}
</div>{js}</body></html>"""


if __name__ == "__main__":
    here = Path(__file__).parent
    for name, is_print in (("index.html", False), ("print.html", True)):
        PRINT = is_print
        (here / name).write_text(build(), encoding="utf-8")
        log(f"wrote {here / name}")
