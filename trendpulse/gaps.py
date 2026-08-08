from __future__ import annotations

from collections import defaultdict

from trendpulse.storage import Store


def own_domains(cfg: dict) -> set[str]:
    domains = {d.lower().removeprefix("www.") for d in cfg.get("brand_domains", [])}
    asset = cfg.get("profound", {}).get("asset", "")
    if asset:
        domains.add(asset.lower().removeprefix("www."))
    return domains


def competitor_domains(cfg: dict) -> set[str]:
    return {d.lower().removeprefix("www.") for d in cfg.get("competitor_domains", [])}


def citation_summary(store: Store, cfg: dict, days: int = 30
                     ) -> list[tuple[str, int, float, str]]:
    """(domain, citations, share %, role) where role is own/competitor/other."""
    rows = store.citation_rows(days)
    own, competitors = own_domains(cfg), competitor_domains(cfg)
    counts: dict[str, int] = defaultdict(int)
    for _date, _url, domain, _prompt, _model in rows:
        counts[domain] += 1
    total = sum(counts.values()) or 1

    def role(domain: str) -> str:
        if any(domain == d or domain.endswith("." + d) for d in own):
            return "own"
        if any(domain == d or domain.endswith("." + d) for d in competitors):
            return "competitor"
        return "other"

    return sorted(
        ((d, c, 100.0 * c / total, role(d)) for d, c in counts.items()),
        key=lambda r: r[1], reverse=True,
    )


def citation_gaps(store: Store, cfg: dict, days: int = 30, limit: int = 10
                  ) -> list[dict]:
    """Prompts where AI engines cite sources but never ours — the GEO content
    backlog, ranked by how often the prompt's answers cite anyone."""
    own = own_domains(cfg)
    by_prompt: dict[str, dict] = {}
    for date, _url, domain, prompt, model in store.citation_rows(days):
        entry = by_prompt.setdefault(prompt, {
            "prompt": prompt, "domains": set(), "models": set(),
            "citations": 0, "last_seen": date, "cites_us": False,
        })
        entry["citations"] += 1
        entry["models"].add(model or "AI")
        entry["last_seen"] = max(entry["last_seen"], date)
        if any(domain == d or domain.endswith("." + d) for d in own):
            entry["cites_us"] = True
        else:
            entry["domains"].add(domain)

    gaps = [e for e in by_prompt.values() if not e["cites_us"] and e["domains"]]
    gaps.sort(key=lambda e: (e["citations"], e["last_seen"]), reverse=True)
    for entry in gaps:
        entry["domains"] = sorted(entry["domains"])[:4]
        entry["models"] = sorted(entry["models"])
    return gaps[:limit]
