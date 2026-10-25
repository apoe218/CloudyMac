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
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import quote

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
        ("ESPN", "https://www.espn.com/espn/rss/ncf/news"),
        ("Google News", "https://news.google.com/rss/search?q=" + quote('"Texas A&M" football when:3d')
         + "&hl=en-US&gl=US&ceid=US:en"),
    ],
    "sec": [
        ("Google News", "https://news.google.com/rss/search?q=" + quote("SEC football when:2d")
         + "&hl=en-US&gl=US&ceid=US:en"),
    ],
    "lfc": [
        ("The Guardian", "https://www.theguardian.com/football/liverpool/rss"),
        ("Google News", "https://news.google.com/rss/search?q=" + quote("Liverpool FC when:2d")
         + "&hl=en-US&gl=US&ceid=US:en"),
    ],
    "football": [
        ("The Guardian", "https://www.theguardian.com/football/premierleague/rss"),
        ("The Guardian", "https://www.theguardian.com/football/championsleague/rss"),
        ("ESPN", "https://www.espn.com/espn/rss/soccer/news"),
    ],
    "national": [("NYT", "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml")],
    "world": [("BBC", "https://feeds.bbci.co.uk/news/world/rss.xml")],
}
# ---------------------------------------------------------------------------


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
BLOCK = re.compile(r"Engines of Our Ingenuity|Sponsored|Crossword|Wordle", re.I)


def collect(feed_list, limit, per_feed=None, max_age_hours=None):
    """Merge feeds, dedupe on title, newest first (round-robin so one source can't hog)."""
    now = datetime.now(timezone.utc)
    buckets = []
    for source, url in feed_list:
        try:
            items = parse_rss(fetch(url), source)
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
        cls = "story lede" if (lede and n == 0) else "story"
        d = clip(it["desc"], 260 if (lede and n == 0) else desc_len) if desc_len else ""
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
        body = "".join(f"<p>{esc(clip(x, 520))}</p>" for x in paras[:3])
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
.tbl th{text-align:left;font-size:10px;letter-spacing:.08em;text-transform:uppercase;border-bottom:2px solid var(--rule);padding:3px 4px}
.tbl td{padding:3px 4px;border-bottom:1px solid var(--hair)}.tbl td:first-child{width:24px;color:var(--muted)}
.tbl tr.me td{font-weight:800;background:rgba(155,28,28,.1)}.tbl tr.gap td{text-align:center;color:var(--muted)}
.aggie-tbl tr.me td{background:rgba(80,0,0,.12)}.rk{font-size:9px;color:var(--accent);font-weight:700}
.sub{font:800 11px var(--sans);letter-spacing:.1em;text-transform:uppercase;margin:12px 0 2px}
.foot{margin-top:8px;border-top:4px double var(--rule);padding-top:8px;font:11px var(--sans);color:var(--muted);
display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap}
@media(max-width:900px){.grid{grid-template-columns:1fr}.col{padding:0;border-left:0}.sheet{padding:12px 14px}}
@media print{body{background:#fff}.sheet{box-shadow:none;max-width:none}}
"""


def build():
    now = datetime.now(CT)
    wx, now_line = weather_section()

    log("fetching news...")
    houston = collect(FEEDS["houston"], 7, per_feed=6, max_age_hours=72)
    aggie_news = collect(FEEDS["aggies"], 6, per_feed=5, max_age_hours=96)
    sec_news = collect(FEEDS["sec"], 5, per_feed=5, max_age_hours=60)
    lfc_news = collect(FEEDS["lfc"], 6, per_feed=5, max_age_hours=96)
    fb_news = collect(FEEDS["football"], 6, per_feed=4, max_age_hours=72)
    nat = collect(FEEDS["national"], 5, max_age_hours=48)
    world = collect(FEEDS["world"], 5, max_age_hours=48)

    log("fetching sports data...")
    ag = aggies_section()
    lv = liverpool_section()

    edition = now.strftime("%A, %B %-d, %Y")
    updated = now.strftime("%-I:%M %p CT")
    ag_rank = f"<span>{esc(ag['rank'])}</span>" if ag["rank"] else ""

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>The H-Town Observer &mdash; {esc(edition)}</title>
<meta name="description" content="A daily front page for Houston weather, Texas A&amp;M, the SEC, Liverpool and the world.">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Libre+Baskerville:wght@400;700&amp;family=Playfair+Display:wght@700;900&amp;family=UnifrakturCook:wght@700&amp;display=swap" rel="stylesheet">
<style>{CSS}</style></head>
<body><div class="sheet">
<div class="topline"><span>Houston, Texas</span><span>Weather &middot; Aggies &middot; The Reds &middot; The World</span><span>Edition no. {now.timetuple().tm_yday}</span></div>
<header class="mast"><h1>The H-Town Observer</h1>
<div class="tag">&ldquo;All the weather, all the Aggies, all the Reds &mdash; fit to print.&rdquo;</div></header>
<div class="dateline"><span>{esc(edition)}</span><span>{now_line}</span><span>Updated {esc(updated)}</span></div>

<div class="grid">
<!-- Column 1: weather + local + world -->
<div class="col">
<section class="sec"><div class="kicker sky">Weather <span>via Space City Weather &amp; NWS</span></div>
{wx['lead']}{wx['alerts']}{wx['forecast']}{wx['now']}{wx['tropics']}</section>
<section class="sec"><div class="kicker">Around Houston</div>{story_list(houston, lede=True)}</section>
<section class="sec"><div class="kicker">The Nation &amp; the World</div>
{story_list(nat[:4] + world[:4], desc_len=140)}</section>
</div>

<!-- Column 2: Aggies + SEC -->
<div class="col">
<section class="sec"><div class="kicker aggie">Gig &rsquo;Em &middot; Texas A&amp;M Football {ag_rank}</div>
{ag['sched']}
<div class="sub">SEC Standings</div><div class="aggie-tbl">{ag['sec']}</div></section>
<section class="sec"><div class="kicker aggie">Aggie Report</div>{story_list(aggie_news, lede=True)}</section>
<section class="sec"><div class="kicker aggie">Around the SEC &amp; College Football</div>{story_list(sec_news, desc_len=0)}</section>
</div>

<!-- Column 3: Liverpool + football -->
<div class="col">
<section class="sec"><div class="kicker lfc">You&rsquo;ll Never Walk Alone &middot; Liverpool FC</div>
{lv['sched']}
<div class="sub">Premier League</div>{lv['epl']}
<div class="sub">Champions League &middot; League Phase</div>{lv['ucl']}</section>
<section class="sec"><div class="kicker lfc">Anfield Report</div>{story_list(lfc_news, lede=True)}</section>
<section class="sec"><div class="kicker lfc">Premier League &amp; Europe</div>{story_list(fb_news, desc_len=0)}</section>
</div>
</div>

<footer class="foot"><span>Compiled automatically each morning from Space City Weather, NWS, NHC, ESPN, The Guardian, BBC, NYT, Houston Public Media, KPRC and Google News.</span>
<span>Headlines link to the original publishers.</span></footer>
</div></body></html>"""


if __name__ == "__main__":
    out = Path(__file__).with_name("index.html")
    out.write_text(build(), encoding="utf-8")
    log(f"wrote {out}")
