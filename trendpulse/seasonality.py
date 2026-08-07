from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta


@dataclass
class SeasonalEvent:
    """A recurring regional moment that moves banking/search demand in the
    GCC (Ramadan, Eid, DSF, salary cycles, ...). Hijri-based dates shift
    every year, so those are marked expected=True — verify against official
    moon-sighting announcements before publishing."""
    name: str
    start: date
    end: date | None = None
    prep_weeks: int = 4
    regions: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    action: str = ""
    expected: bool = False

    def is_active(self, today: date) -> bool:
        return self.start <= today <= (self.end or self.start)

    def days_until(self, today: date) -> int:
        return (self.start - today).days

    def in_prep_window(self, today: date) -> bool:
        return self.start - timedelta(weeks=self.prep_weeks) <= today < self.start


def load_events(cfg: dict) -> list[SeasonalEvent]:
    events = []
    for raw in cfg.get("seasonal_events", []) or []:
        events.append(SeasonalEvent(
            name=raw["name"],
            start=date.fromisoformat(str(raw["start"])),
            end=date.fromisoformat(str(raw["end"])) if raw.get("end") else None,
            prep_weeks=int(raw.get("prep_weeks", 4)),
            regions=list(raw.get("regions", [])),
            keywords=list(raw.get("keywords", [])),
            action=raw.get("action", ""),
            expected=bool(raw.get("expected", False)),
        ))
    return events


def upcoming_events(cfg: dict, today: date, within_days: int = 90) -> list[SeasonalEvent]:
    """Events active now or starting within `within_days`, soonest first."""
    horizon = today + timedelta(days=within_days)
    return sorted(
        (e for e in load_events(cfg)
         if e.is_active(today) or today <= e.start <= horizon),
        key=lambda e: e.start,
    )


def prep_keywords(cfg: dict, today: date) -> list[tuple[str, str]]:
    """(keyword, event_name) pairs for events active or inside their prep
    window — injected into the tracked universe during daily ingest."""
    out: list[tuple[str, str]] = []
    for event in load_events(cfg):
        if event.is_active(today) or event.in_prep_window(today):
            out.extend((kw, event.name) for kw in event.keywords)
    return out
