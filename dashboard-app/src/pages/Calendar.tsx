import { useData } from "../lib/data";
import { Badge, Card, Empty, Reveal, SectionHead } from "../components/ui";

export default function Calendar() {
  const { data } = useData();
  if (!data) return null;

  const fmt = (iso: string) =>
    new Date(iso + "T00:00:00").toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });

  return (
    <>
      <SectionHead eyebrow="Plan ahead" title="Upcoming regional moments"
        note="Content must rank before the moment, not during it. Dates marked ~ follow the Hijri calendar — verify against official announcements before publishing." />
      {data.events.length === 0 ? <Card><Empty text="Nothing on the calendar for the next 120 days." /></Card> : (
        <Reveal className="space-y-3.5">
          {data.events.map((e) => (
            <Card key={e.name} className="relative overflow-hidden">
              <div className="absolute inset-y-0 left-0 w-1"
                style={{ background: e.active ? "var(--good)" : e.prepNow ? "var(--warn)" : "var(--border)" }} aria-hidden />
              <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 pl-2">
                <span className="tnum text-[13px] font-semibold text-ink2">
                  {e.expected && "~"}{fmt(e.start)}{e.end ? ` → ${fmt(e.end)}` : ""}
                </span>
                <span className="text-[15px] font-bold">{e.name}</span>
                {e.active && <Badge tone="rising">active now</Badge>}
                {!e.active && e.prepNow && <Badge tone="hot">prep window is NOW</Badge>}
                {!e.active && !e.prepNow && <Badge tone="cooling">in {e.daysUntil} days</Badge>}
                {e.regions.length > 0 && <span className="text-xs text-ink2">{e.regions.join(", ")}</span>}
              </div>
              {e.action && <p className="mt-1.5 pl-2 text-[13.5px] leading-relaxed text-ink2">{e.action}</p>}
              {e.keywords.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1.5 pl-2">
                  {e.keywords.map((k) => <Badge key={k} tone="chip">{k}</Badge>)}
                </div>
              )}
            </Card>
          ))}
        </Reveal>
      )}
    </>
  );
}
