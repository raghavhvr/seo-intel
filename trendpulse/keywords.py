from __future__ import annotations

import re

from trendpulse.storage import Store

CHANNELS = ("seo", "aeo", "geo")

QUESTION_PREFIXES = (
    # English
    "how ", "what ", "why ", "when ", "where ", "which ", "who ",
    "can ", "is ", "are ", "does ", "do ", "should ",
    # Arabic — كيف/ما/ماذا/لماذا/هل/متى/أين/كم/من
    "كيف ", "ما ", "ماذا ", "لماذا ", "هل ", "متى ", "أين ", "اين ",
    "كم ", "من ",
)

DEFAULT_GEO_TERMS = {
    "ai", "llm", "chatgpt", "openai", "claude", "gemini", "perplexity",
    "copilot", "agent", "agents", "generative", "prompt", "rag",
    "language model", "ai search", "ai overview",
}

# Latin + Arabic (main block, supplement, extended-A) + digits; strips
# everything else, including Arabic diacritics (tashkeel).
_ARABIC = r"؀-ۿݐ-ݿࢠ-ࣿ"
_TASHKEEL_RE = re.compile(r"[ً-ْٰ]")  # Arabic diacritics + superscript alef
_CLEAN_RE = re.compile(r"[^a-z0-9" + _ARABIC + r" +\-/&']+")
_TRAILING_RE = re.compile(r"[\s\-/&]+$")


def normalize(text: str) -> str:
    text = _TASHKEEL_RE.sub("", text.strip().lower())
    text = _CLEAN_RE.sub("", text)
    text = re.sub(r"\s+", " ", text).strip()
    return _TRAILING_RE.sub("", text)


def is_question(keyword: str) -> bool:
    kw = keyword.lower().strip()
    if kw.endswith("?"):
        return True
    return any(kw.startswith(p) or f" {p.strip()} " in f" {kw} " for p in QUESTION_PREFIXES)


def is_geo_relevant(keyword: str, geo_terms: list[str] | None = None) -> bool:
    terms = {t.lower() for t in (geo_terms or [])} | DEFAULT_GEO_TERMS
    kw = f" {keyword.lower()} "
    return any(f" {t} " in kw or kw.strip().startswith(t + " ") for t in terms)


def channels_for(keyword: str, cfg: dict, seed_channel: str | None = None) -> set[str]:
    """Every keyword is SEO-relevant; questions are AEO-relevant; AI-flavoured
    topics are GEO-relevant. A seed's config section adds its channel too."""
    channels = {"seo"}
    if is_question(keyword):
        channels.add("aeo")
    if is_geo_relevant(keyword, cfg.get("geo_terms")):
        channels.add("geo")
    if seed_channel in CHANNELS:
        channels.add(seed_channel)
    return channels


def seed_keywords(cfg: dict) -> dict[str, str]:
    """{keyword: seed_channel} from the config's seeds section."""
    out: dict[str, str] = {}
    for channel in CHANNELS:
        for kw in cfg.get("seeds", {}).get(channel, []) or []:
            norm = normalize(kw)
            if norm:
                out[norm] = channel
    return out


def valid_candidate(keyword: str) -> bool:
    if not keyword or len(keyword) < 3 or len(keyword) > 80:
        return False
    if keyword.count(" ") > 8:
        return False
    return True


STOPWORDS = {
    "the", "a", "an", "in", "on", "of", "for", "to", "and", "or", "vs",
    "how", "what", "why", "when", "is", "are", "do", "does", "can", "best",
    "في", "من", "ما", "هل", "كيف", "أفضل", "الى", "على", "أين", "متى",
}


def universe_tokens(keywords) -> set[str]:
    tokens: set[str] = set()
    for kw in keywords:
        tokens.update(t for t in normalize(kw).split() if t not in STOPWORDS)
    return tokens


def is_relevant(keyword: str, tokens: set[str], cfg: dict) -> bool:
    """Gate for folding discoveries into the tracked universe: keeps
    question-shaped and GEO-relevant finds plus anything sharing vocabulary
    with the existing universe (e.g. 'uae', 'credit', 'card'). Global
    front-page noise fails all three checks."""
    if is_question(keyword) or is_geo_relevant(keyword, cfg.get("geo_terms")):
        return True
    toks = {t for t in keyword.split() if t not in STOPWORDS}
    return bool(toks & tokens)


def keyword_universe(cfg: dict, store: Store) -> dict[str, str | None]:
    """Seeds plus the best auto-discovered keywords, capped by config.

    Returns {keyword: seed_channel_or_None}.
    """
    universe: dict[str, str | None] = dict(seed_keywords(cfg))
    cap = int(cfg["keywords"]["max_universe"])
    for kw, _score in store.discovered_keywords(limit=cap * 3):
        if len(universe) >= cap:
            break
        norm = normalize(kw)
        if valid_candidate(norm) and norm not in universe:
            universe[norm] = None
    return universe
