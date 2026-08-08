from __future__ import annotations

import logging
from datetime import datetime, timezone

from trendpulse.storage import Store
from trendpulse.types import Discovery, EntityMention

log = logging.getLogger(__name__)


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")

ALIASES = {
    "adcb": ["adcb", "abu dhabi commercial bank", "بنك أبوظبي التجاري"],
    "fab": ["fab", "first abu dhabi bank", "بنك أبوظبي الأول"],
    "emirates nbd": ["emirates nbd", "emiratesnbd", "enbd", "بنك الإمارات دبي الوطني"],
    "wio": ["wio"],
    "liv": ["liv", "liv."],
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
    share-of-voice from Reddit threads, news headlines, HN stories."""
    import re

    entities = cfg.get("entities", {})
    groups = {"brand": entities.get("brand", []),
              "competitor": entities.get("competitors", [])}
    patterns = {entity: (kind, re.compile(_expand_aliases([entity])[entity], re.IGNORECASE))
                for kind, names in groups.items() for entity in names}
    if not patterns:
        return 0

    date = _today()
    mentions: list[EntityMention] = []
    for disc in discoveries:
        haystack = f"{disc.keyword} {disc.context}".lower()
        for entity, (kind, rx) in patterns.items():
            if rx.search(haystack):
                mentions.append(EntityMention(
                    date=date, entity=entity, kind=kind, source=disc.source,
                    context=disc.context[:150], value=max(disc.score, 1.0)))
    written = store.upsert_entity_mentions(mentions)
    if written:
        log.info("[entities] %d brand/competitor mentions in today's discoveries", written)
    return written
