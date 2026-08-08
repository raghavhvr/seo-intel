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
    # "ai" is too generic to establish banking relevance on its own: with it,
    # every trending model name ("kimi ai") ties itself to the universe
    # through the seed "ai in banking".
    "ai",
    "في", "من", "ما", "هل", "كيف", "أفضل", "الى", "على", "أين", "متى",
}


def universe_tokens(keywords) -> set[str]:
    tokens: set[str] = set()
    for kw in keywords:
        tokens.update(t for t in normalize(kw).split() if t not in STOPWORDS)
    return tokens


def is_relevant(keyword: str, tokens: set[str], cfg: dict) -> bool:
    """Gate for folding discoveries into the tracked universe: everything must
    share vocabulary with it (e.g. 'credit', 'card', 'loan', 'banking').

    Neither being question-shaped nor being AI-flavored is sufficient on its
    own. Community feeds are full of off-topic questions ('which gym is this'),
    and the GEO sources (Hugging Face trending, HN) are full of AI topics with
    zero banking connection — an unconditional GEO pass once put 'flux1
    schnell', an image-generation model, at the top of a bank's SEO focus
    list. An AI topic earns its place the same way everything else does: by
    overlapping the banking vocabulary ('ai in banking' does; 'kimi ai' does
    not)."""
    toks = {t for t in keyword.split() if t not in STOPWORDS}
    return bool(toks & tokens)


def keyword_universe(cfg: dict, store: Store) -> dict[str, str | None]:
    """Seeds plus the best auto-discovered keywords, capped by config.

    Discoveries are admitted only when relevant to the SEED vocabulary — this
    is the universe's actual door, and it used to stand open: any discovery up
    to the cap entered untested, which is how Hugging Face trending-model
    names became tracked 'banking' keywords. Gating against seed tokens
    (rather than the growing universe) also stops drift: one admitted stray
    cannot vouch for the next via its own vocabulary.

    Returns {keyword: seed_channel_or_None}, in priority order — seeds first,
    then discoveries by score (collectors cap request volume with
    keywords[:N], so iteration order is the ingestion priority).
    """
    universe: dict[str, str | None] = dict(seed_keywords(cfg))
    tokens = universe_tokens(universe)
    cap = int(cfg["keywords"]["max_universe"])
    for kw, _score in store.discovered_keywords(limit=cap * 3):
        if len(universe) >= cap:
            break
        norm = normalize(kw)
        if (valid_candidate(norm) and norm not in universe
                and is_relevant(norm, tokens, cfg)):
            universe[norm] = None
    return universe
