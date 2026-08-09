from __future__ import annotations

import logging
from datetime import datetime, timezone

from trendpulse.storage import Store
from trendpulse.types import Discovery, EntityMention

log = logging.getLogger(__name__)


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")

ALIASES = {
    "adcb": ["adcb", "abu dhabi commercial bank", "بنك أبوظبي التجاري",
             "أبوظبي التجاري", "بنك أبوظبي تجاري"],
    "fab": ["fab", "first abu dhabi bank", "fab bank", "fab islamic", "nbad",
            "بنك أبوظبي الأول", "أبوظبي الأول", "بنك أبو ظبي الأول"],
    "emirates nbd": ["emirates nbd", "emiratesnbd", "enbd",
                     "بنك الإمارات دبي الوطني", "الإمارات دبي الوطني",
                     "بنك الإمارات ندب"],
    "dubai islamic bank": ["dubai islamic bank", "dib", "بنك دبي الإسلامي",
                           "دبي الإسلامي", "مصرف دبي الإسلامي"],
    "mashreq": ["mashreq", "mashreq bank", "mashreq neo", "المشرق", "بنك المشرق",
                "مشرق"],
    "rakbank": ["rakbank", "rak bank", "national bank of ras al khaimah",
                "بنك رأس الخيمة الوطني", "راك بنك", "بنك راس الخيمة الوطني"],
    "commercial bank of dubai": ["commercial bank of dubai", "cbd",
                                 "بنك دبي التجاري", "بنك تجاري دبي"],
    "hsbc uae": ["hsbc uae", "hsbc", "بنك إتش إس بي سي", "إتش إس بي سي",
                 "hsbc الإمارات", "hsbc amanah"],
    "adib": ["adib", "abu dhabi islamic bank", "بنك أبوظبي الإسلامي",
             "مصرف أبوظبي الإسلامي", "أبوظبي الإسلامي"],
    "emirates islamic": ["emirates islamic", "emirates islamic bank",
                         "الإمارات الإسلامي", "بنك الإمارات الإسلامي",
                         "مصرف الإمارات الإسلامي"],
    "wio": ["wio", "wio bank", "wio personal", "wio business", "بنك ويو"],
    "liv": ["liv", "liv.", "liv bank", "liv x"],
}

# Preferred display name per alias group — what the rolled-up tables show.
DISPLAY = {
    "adcb": "ADCB", "fab": "FAB", "emirates nbd": "Emirates NBD",
    "dubai islamic bank": "Dubai Islamic Bank", "mashreq": "Mashreq",
    "rakbank": "RAKBANK", "commercial bank of dubai": "Commercial Bank of Dubai",
    "hsbc uae": "HSBC UAE", "adib": "ADIB", "emirates islamic": "Emirates Islamic",
    "wio": "Wio", "liv": "Liv",
}


def _expand_aliases(entities: list[str]) -> dict[str, str]:
    """{canonical: regex} with built-in alias expansion for common UAE banks."""
    import re

    out: dict[str, str] = {}
    for entity in entities:
        names = ALIASES.get(entity.lower(), [entity])
        if entity not in names:
            names = [entity, *names]
        pattern = "|".join(re.escape(n.lower()) for n in names)
        out[entity] = rf"(?<![a-z0-9])(?:{pattern})(?![a-z0-9])"
    return out


def canonicalizer(cfg: dict):
    """name -> (display_name, kind) for any raw entity string.

    'ADCB', 'Abu Dhabi Commercial Bank' and 'بنك أبوظبي التجاري' are one bank;
    so are 'FAB', 'First Abu Dhabi Bank', 'FAB Bank' and 'بنك أبوظبي الأول'.
    Sources report whichever surface form the text used (Profound stores the
    name verbatim from each AI answer), and the config itself lists aliases as
    separate entries — without canonicalization the share-of-voice table both
    fragments one bank across several rows AND double-counts sightings that
    match two alias entries. Unknown names pass through unchanged (kind
    'competitor'), so auto-discovered entities like Ruya or Sarwa still show.
    """
    import re

    brand_names = (cfg.get("entities", {}) or {}).get("brand", [])
    brand_display = brand_names[0] if brand_names else "brand"
    groups: list[tuple[str, str, re.Pattern]] = []

    def pattern(names: list[str]) -> re.Pattern:
        alts = "|".join(re.escape(n.lower()) for n in sorted(names, key=len, reverse=True))
        return re.compile(rf"(?<![a-z0-9])(?:{alts})(?![a-z0-9])")

    brand_alias = set(n.lower() for n in brand_names)
    for key, names in ALIASES.items():
        display = DISPLAY.get(key, key.title())
        kind = "brand" if (key in brand_alias or brand_alias & set(names)) else "competitor"
        if kind == "brand":
            display = brand_display
        groups.append((display, kind, pattern(names)))
    # Config competitors not covered by the built-in alias table.
    covered = {n for names in ALIASES.values() for n in names}
    for comp in (cfg.get("entities", {}) or {}).get("competitors", []):
        if comp.lower() not in covered:
            groups.append((comp, "competitor", pattern([comp])))

    def canon(name: str) -> tuple[str, str]:
        low = f" {str(name).lower().strip()} "
        for display, kind, rx in groups:
            if rx.search(low):
                return display, kind
        return str(name).strip(), "competitor"

    return canon


def rolled_up_split(store: Store, cfg: dict, days: int = 7
                    ) -> list[tuple[str, str, float, float]]:
    """entity_mention_split with alias groups merged: one row per bank,
    (display, kind, ai_mentions, community_mentions), sorted by total."""
    canon = canonicalizer(cfg)
    merged: dict[str, list] = {}
    for entity, kind, ai, community in store.entity_mention_split(days=days):
        display, ckind = canon(entity)
        row = merged.setdefault(display, [display, ckind, 0.0, 0.0])
        if ckind == "brand" or kind == "brand":
            row[1] = "brand"
        row[2] += ai
        row[3] += community
    return sorted((tuple(r) for r in merged.values()),
                  key=lambda r: r[2] + r[3], reverse=True)


def rolled_up_visibility(store: Store, cfg: dict, days: int = 7
                         ) -> list[tuple[str, str, float, float]]:
    """entity_visibility with alias groups merged:
    (display, kind, mentions, share_of_voice %)."""
    rows = rolled_up_split(store, cfg, days=days)
    total = sum(ai + com for _d, _k, ai, com in rows) or 1.0
    return [(d, k, ai + com, 100.0 * (ai + com) / total) for d, k, ai, com in rows]


def competitor_matcher(cfg: dict):
    """A predicate marking keywords that sit in a competitor's branded
    territory ('mashreq neo account', 'emirates nbd balance check'). The
    report and dashboard use it to switch the recommendation from 'create a
    page' — pointless advice for someone else's brand — to a comparison play,
    and to keep such terms out of the top-opportunity cards."""
    import re

    competitors = (cfg.get("entities", {}) or {}).get("competitors", [])
    if not competitors:
        return lambda keyword: False
    expanded = _expand_aliases(competitors)
    pattern = re.compile("|".join(f"(?:{p})" for p in expanded.values()),
                         re.IGNORECASE)
    return lambda keyword: bool(pattern.search(keyword.lower()))


def is_brand_mention(name: str, asset: str) -> bool:
    """True when an AI-answer mention refers to the brand asset: the asset
    domain ('adcb.com'), its stem ('adcb'), or the asset's own alias list
    ('Abu Dhabi Commercial Bank', بنك أبوظبي التجاري)."""
    text = name.lower()
    target = asset.lower().replace("www.", "")
    if target and (target in text or text in target):
        return True
    stem = target.split(".")[0]
    if stem and stem in text:
        return True
    return any(alias in text for alias in ALIASES.get(stem, []))


def scan_discoveries(cfg: dict, store: Store, discoveries: list[Discovery]) -> int:
    """Scan today's discoveries for brand/competitor mentions — community
    share-of-voice from Reddit threads, news headlines, HN stories.

    Matching runs per ALIAS GROUP, not per config entry: 'FAB' and 'First Abu
    Dhabi Bank' are one bank, and matching them as two entities wrote two
    mention rows for a single sighting — double-counting the exact number the
    share-of-voice table sums. One sighting now yields at most one mention per
    bank, stored under its canonical display name, at value 1.0 (discovery
    scores are not comparable across sources; a pytrends breakout number once
    credited ADCB with 446k 'mentions')."""
    canon = canonicalizer(cfg)
    entities = cfg.get("entities", {})
    watch = list(entities.get("brand", [])) + list(entities.get("competitors", []))
    if not watch:
        return 0
    patterns = _expand_aliases(watch)
    import re
    compiled = [re.compile(p, re.IGNORECASE) for p in patterns.values()]

    date = _today()
    mentions: list[EntityMention] = []
    for disc in discoveries:
        haystack = f"{disc.keyword} {disc.context}".lower()
        seen: set[str] = set()
        for rx in compiled:
            match = rx.search(haystack)
            if not match:
                continue
            display, kind = canon(match.group(0))
            if display in seen:
                continue
            seen.add(display)
            mentions.append(EntityMention(
                date=date, entity=display, kind=kind, source=disc.source,
                context=disc.context[:150], value=1.0))
    written = store.upsert_entity_mentions(mentions)
    # Retroactive for history already collected under the old weighting: a
    # 'mention'-metric value above 1 is always a discovery-score artifact.
    store.clamp_mention_values()
    if written:
        log.info("[entities] %d brand/competitor mentions in today's discoveries", written)
    return written
