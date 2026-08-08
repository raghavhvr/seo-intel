"""Keyword -> Wikipedia article matching, with a relevance gate.

Wikipedia's search API always returns *something*. Taking its top hit on trust
is how "how to check credit score in uae" ends up tracking the pageviews of
"The Diplomat (2025 film)", and "الدرهم الرقمي" (digital dirham) ends up
tracking درهم مغربي — the *Moroccan* dirham. Those series then feed the blended
attention score as if they were demand signal.

The gate here is deliberately strict: a candidate article is accepted only when
its title accounts for every meaningful token of the keyword. Market words
("uae", "الإمارات") and intent words ("best", "how", "online") are stripped
first, because they describe *who is asking*, not *what the article is about* —
no encyclopaedia article is titled "Credit card UAE".

Being strict means most localized commercial queries resolve to nothing, and
that is the correct outcome: Wikipedia has no article for "car loan uae", so
the honest number of observations for it is zero, not the pageviews of the
nearest unrelated page. Where a mapping *is* genuinely useful, curate it
explicitly via `wikipedia.articles` in config.yaml.
"""
from __future__ import annotations

import logging
import re

from trendpulse.keywords import STOPWORDS, normalize

log = logging.getLogger(__name__)

# Market/geo words. They express where the searcher is, and never appear in the
# title of the concept article they are asking about.
GEO_TOKENS = {
    "uae", "emirates", "emirati", "dubai", "abu", "dhabi", "sharjah", "ajman",
    "gcc", "gulf", "ksa", "saudi", "arabia", "qatar", "kuwait", "bahrain",
    "oman", "jordan", "lebanon", "mena",
    "الإمارات", "الامارات", "دبي", "أبوظبي", "ابوظبي", "الشارقة", "السعودية",
    "قطر", "الكويت", "البحرين", "عمان", "الأردن", "لبنان", "الخليج",
}

# Intent/modifier words: they shape the query, not the subject.
INTENT_TOKENS = {
    "best", "top", "cheap", "cheapest", "lowest", "highest", "compare",
    "comparison", "online", "near", "me", "apply", "open", "get", "check",
    "calculate", "calculator", "rates", "rate", "offers", "deals", "requirements",
    "eligibility", "minimum", "maximum", "today", "2025", "2026", "review",
    "reviews", "free", "instant", "quick", "easy", "guide", "tips",
    "أفضل", "أرخص", "مقارنة", "أونلاين", "حاسبة", "شروط", "عروض", "مجاني",
}

_AL = re.compile(r"^ال")


def _tokens(text: str) -> set[str]:
    """Normalized tokens with the Arabic definite article stripped, so
    'الدرهم' and 'درهم' compare equal."""
    return {_AL.sub("", t) for t in normalize(text).split() if t}


def content_tokens(keyword: str) -> set[str]:
    """The tokens that actually name the subject of the keyword.

    Word lists are applied to the *unstripped* tokens (they are written with
    the definite article, e.g. 'الإمارات'), and ال is stripped only afterwards,
    for comparison against article titles.
    """
    kept = [
        t for t in normalize(keyword).split()
        if t and t not in STOPWORDS and t not in GEO_TOKENS and t not in INTENT_TOKENS
    ]
    return {_AL.sub("", t) for t in kept}


def matches(keyword: str, title: str) -> bool:
    """True when `title` covers every content token of `keyword`.

    Full coverage — not partial overlap — is what separates a real match from a
    plausible-looking wrong one. 'digital dirham' shares 'dirham' with both
    'UAE dirham' and 'Moroccan dirham'; only full coverage rejects both, which
    is right, since neither article is about a CBDC.

    A single-token subject additionally has to match the title exactly.
    Coverage alone is too easy to satisfy when the subject is one generic word:
    'أفضل بنك في الإمارات' ("best bank in the UAE") reduces to {بنك} ("bank"),
    which any named bank's article covers — it resolved to بنك عوده, a Lebanese
    bank. With one word to go on, the article must *be* the concept rather than
    an instance of it.

    The gate errs towards rejection on purpose. A false accept injects an
    unrelated article's traffic into the trend score; a false reject costs one
    series of global, non-geo-filtered pageviews, and `wikipedia.articles`
    exists to restore any that are genuinely worth keeping.
    """
    wanted = content_tokens(keyword)
    if not wanted:
        return False
    found = _tokens(title)
    if not wanted <= found:
        return False
    return len(wanted) >= 2 or found == wanted


def best_match(keyword: str, candidates: list[str]) -> str | None:
    """The narrowest candidate that clears the gate, so the article is about
    the subject itself rather than a sub-topic of it: for 'credit card uae',
    'Credit card' wins over 'Credit card fraud'."""
    passing = [c for c in candidates if matches(keyword, c)]
    if not passing:
        return None
    return min(passing, key=lambda c: (len(_tokens(c)), len(c)))


def configured_article(cfg: dict, keyword: str, lang: str) -> str | None:
    """Explicit operator override from config: `wikipedia.articles`.

    Accepts either a flat {keyword: title} map (applies to every edition) or a
    per-language {lang: {keyword: title}} map. Curated mappings bypass the gate
    entirely — a human has already vouched for them.
    """
    articles = (cfg.get("wikipedia") or {}).get("articles") or {}
    per_lang = articles.get(lang)
    if isinstance(per_lang, dict):
        hit = per_lang.get(keyword) or per_lang.get(normalize(keyword))
        if hit:
            return str(hit)
    hit = articles.get(keyword) or articles.get(normalize(keyword))
    return str(hit) if isinstance(hit, str) else None


def prune_stale_observations(cfg: dict, store) -> int:
    """Delete stored Wikipedia observations whose article fails today's gate.

    The gate only stops *new* bad mappings. History already collected under a
    wrong mapping keeps feeding the blended score for as long as its 60-day
    backfill window survives — so a bank's 'how to send money from uae to
    india' series went on tracking "United Arab Emirates in the 2026 Iran war"
    long after the matcher had been fixed. Re-checking on every ingest makes
    the fix retroactive, and makes a later edit to `wikipedia.articles` clean
    up after itself.

    Deletion is confined to Wikipedia rows whose recorded article the current
    config and gate both reject; every removal is logged with its article, and
    the rows regenerate on the next run if a mapping is added for them.
    """
    removed = 0
    for source, keyword, article in store.wikipedia_mappings():
        lang = source.partition("_")[2]
        if configured_article(cfg, keyword, lang) == article or matches(keyword, article):
            continue
        rows = store.delete_observations(source, keyword)
        removed += rows
        log.info("[wikipedia] dropped %d stale observations: %s '%s' -> %r",
                 rows, source, keyword, article)
    return removed
