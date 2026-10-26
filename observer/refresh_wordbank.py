#!/usr/bin/env python3
"""Rebuild observer/wordbank.json from free sources (run occasionally, not daily).

Words, definitions and frequencies come from the free Datamuse API (no key), whose
definitions are drawn from Wiktionary. Each word becomes a dictionary-style crossword
clue. Only everyday-but-not-trivial words are kept so the puzzle plays "medium".
The committed wordbank.json keeps the daily puzzle (and yesterday's solution)
deterministic and independent of the network.
"""
import json
import re
import string
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

API = "https://api.datamuse.com/words?sp={pat}&md=df&max=1000"
FREQ_MIN, FREQ_MAX = 1.0, 70.0   # per-million; below = obscure, above = too easy

BAD_LABEL = re.compile(r"obsolete|archaic|dialect|rare|dated|uk|scotland|australia|canad|ireland|slang|vulgar|"
                       r"offensive|derogatory|computing|chemistry|mathematics|biology|medicine|law|"
                       r"nautical|heraldry|music|physics|geology|botany|zoology|informal|"
                       r"colloquial|pejorative|ethnic|sexual|euphemism|mining|historical|astronomy|"
                       r"anatomy|linguistics|grammar|military|business|sports|games|computer|"
                       r"proscribed|nonstandard|jocular|humorous|literary|india|new zealand|"
                       r"south africa|hong kong|us|american|british|regional|chiefly|north america", re.I)
# grammatical labels are harmless: strip them instead of rejecting the word
GRAMMAR_LABEL = re.compile(r"^(transitive|intransitive|ambitransitive|figurative|usually|often|especially|"
                           r"by extension|countable|uncountable|reflexive|ditransitive|impersonal)"
                           r"([,;]\s*(transitive|intransitive|figurative|by extension|countable|uncountable|reflexive))*$", re.I)
BAD_TEXT = re.compile(r"alternative (form|spelling)|plural of|past (tense|participle)|present participle|"
                      r"third-person|comparative|superlative|initialism|abbreviation|acronym|"
                      r"misspelling|eye dialect|obsolete|vulgar|offensive|derogatory|sexual|genital|erotic|"
                      r"racial|ethnic|prostitut|slur|nazi|kill|murder|suicide|rape|porn|"
                      r"county|village|town|municipality|commune|district|parish|township|river in|"
                      r"\b(UK|US|U\.S\.)\b|England|Scotland|Wales|Ireland|France|Germany|Michigan|"
                      r"\bsee also\b|\bsynonym of\b|\bused (to|in|as)\b|\bof or (relating|pertaining)\b", re.I)
BAD_WORD = re.compile(r"^(?:.*(?:fuck|shit|cunt|nigg|fag|dyke|whore|slut|bitch|bastard|piss|cock|dick|tit|"
                      r"twat|wank|nazi|rape|damn|hell|sex|naked|nude|drunk|bomb|terror|weapon|gun).*)$", re.I)


def fetch(pat):
    for i in range(4):
        try:
            req = urllib.request.Request(API.format(pat=pat), headers={"User-Agent": "HTownObserver/1.0"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read())
        except Exception as e:  # noqa: BLE001
            time.sleep(1.5 * (i + 1))
            last = e
    print(f"gave up on {pat}: {last}", file=sys.stderr)
    return []


def clean(defn, word):
    text = defn.partition("\t")[2].strip()
    while text.startswith("("):
        m = re.match(r"\(([^)]*)\)\s*", text)
        if not m:
            break
        if not GRAMMAR_LABEL.match(m.group(1).strip()) and BAD_LABEL.search(m.group(1)):
            return None
        text = text[m.end():]
    text = re.split(r";|\. |: ", text)[0].strip().rstrip(".,")
    if not (12 <= len(text) <= 62) or BAD_TEXT.search(text):
        return None
    if re.match(r"(often|usually|typically|sometimes|such|of|the act of one|the act of|a person named|this|that|these|those|it|its|he|she)\b", text, re.I):
        return None
    if re.search(r"\b(particular|given name|surname|such|shipping|brand|company|corporation|term for|"
                 r"as (a|an|the)\b|a (male|female))", text, re.I):
        return None
    stem = word[: max(4, len(word) - 3)] if len(word) > 4 else word
    if stem.lower() in text.lower() or word.lower() in text.lower():
        return None
    if text.count("(") != text.count(")") or text.endswith(("(", ",", "-")):
        return None
    if re.search(r"[A-Z]{2,}|\d", text):          # acronyms, numbers
        return None
    if sum(1 for w in text.replace("(", " ").split()[1:] if w[:1].isupper()) > 0:  # proper nouns mid-clue
        return None
    return text[0].upper() + text[1:]


def entry(rec):
    w = rec["word"]
    if not re.fullmatch(r"[a-z]{3,10}", w) or BAD_WORD.match(w):
        return None
    # inflected forms make awkward clues (singular definition, plural answer)
    if (w.endswith("s") and not w.endswith(("ss", "us", "is", "ous"))) or w.endswith(("ed", "ly", "ness", "ing", "swam", "gotten")):
        return None
    f = next((float(t[2:]) for t in rec.get("tags", []) if t.startswith("f:")), None)
    if f is None or not FREQ_MIN <= f <= FREQ_MAX:
        return None
    for d in rec.get("defs", [])[:1]:   # primary sense only, so clues are fair
        c = clean(d, w)
        if c:
            return [w.upper(), c, round(f, 2)]
    return None


def main():
    pats = []
    for n in (3, 4, 5, 6, 7, 8):
        pats += [f"{ch}{'?' * (n - 1)}" for ch in string.ascii_lowercase]
    pats += ["?" * 9, "?" * 10] + [f"{ch}????????" for ch in string.ascii_lowercase]
    out, seen = [], set()
    with ThreadPoolExecutor(6) as ex:
        for recs in ex.map(fetch, pats):
            for rec in recs:
                e = entry(rec)
                if e and e[0] not in seen:
                    seen.add(e[0])
                    out.append(e)
    out.sort(key=lambda e: e[0])
    Path(__file__).with_name("wordbank.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")))
    by_len = {}
    for a, _, _ in out:
        by_len[len(a)] = by_len.get(len(a), 0) + 1
    print(len(out), "entries", dict(sorted(by_len.items())))


if __name__ == "__main__":
    main()
