"""English glosses for Arabic keywords, so non-Arabic readers can act on them.

Two layers:
- A curated dictionary for the shipped seeds and common variants — instant,
  offline, and exactly phrased.
- Google's free translate endpoint (the same class of unofficial endpoint the
  autocomplete collector already relies on) for Arabic keywords the pipeline
  discovers later. Every result is cached forever in the `translations` table,
  so each keyword costs at most one request in its lifetime, and a network
  failure just leaves that keyword unglossed until the next run.
"""
from __future__ import annotations

import logging
import re
import time

from trendpulse.storage import Store

log = logging.getLogger(__name__)

URL = "https://translate.googleapis.com/translate_a/single"

_ARABIC_RE = re.compile(r"[؀-ۿ]")

CURATED = {
    "قرض شخصي الإمارات": "personal loan uae",
    "بطاقة ائتمان الإمارات": "credit card uae",
    "فتح حساب بنكي في الإمارات": "open a bank account in the uae",
    "أفضل بنك في الإمارات": "best bank in the uae",
    "حساب توفير الإمارات": "savings account uae",
    "تحويل أموال من الإمارات": "transfer money from the uae",
    "قرض سيارة الإمارات": "car loan uae",
    "التمويل العقاري الإمارات": "mortgage / home finance uae",
    "كيف أفتح حساب بنكي في الإمارات": "how do i open a bank account in the uae",
    "ما هو الحد الأدنى للراتب للحصول على قرض شخصي":
        "what is the minimum salary for a personal loan",
    "كيف أحول أموال من الإمارات إلى الهند":
        "how do i transfer money from the uae to india",
    "البنوك الرقمية الإمارات": "digital banks uae",
    "الدرهم الرقمي": "the digital dirham",
}


def is_arabic(text: str) -> bool:
    """True when the string is meaningfully Arabic (≥ 30% Arabic letters)."""
    if not text:
        return False
    arabic = len(_ARABIC_RE.findall(text))
    return arabic >= max(2, 0.3 * len(text.replace(" ", "")))


def _fetch(text: str) -> str | None:
    import requests

    try:
        resp = requests.get(URL, params={
            "client": "gtx", "sl": "ar", "tl": "en", "dt": "t", "q": text,
        }, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        resp.raise_for_status()
        segments = resp.json()[0] or []
        joined = "".join(seg[0] for seg in segments if seg and seg[0]).strip()
        return joined or None
    except Exception as exc:  # noqa: BLE001 - a gloss is never worth failing a run
        log.debug("[translate] %r failed: %s", text, exc)
        return None


def glosses(store: Store, texts: list[str]) -> dict[str, str]:
    """{arabic_text: english_gloss} for every Arabic string in `texts`.
    Curated first, then the DB cache, then one network call per novel string
    (throttled). Non-Arabic strings are skipped entirely."""
    wanted = [t for t in dict.fromkeys(texts) if is_arabic(t)]
    if not wanted:
        return {}
    out: dict[str, str] = {}
    misses: list[str] = []
    for text in wanted:
        cached = CURATED.get(text) or store.get_translation(text)
        if cached:
            out[text] = cached
        else:
            misses.append(text)
    for text in misses:
        translated = _fetch(text)
        if translated:
            out[text] = translated
            store.set_translation(text, translated)
        time.sleep(0.1)
    if misses:
        log.info("[translate] %d/%d new Arabic keywords glossed",
                 sum(1 for t in misses if t in out), len(misses))
    return out
