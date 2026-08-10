import { useMemo, useState } from "react";
import { useData, CHANNEL_LABEL, HORIZON_LABEL } from "../lib/data";
import { Badge, Card, Empty, MomentumBadge, SectionHead, press } from "../components/ui";
import { Search } from "lucide-react";

export default function Focus() {
  const { data } = useData();
  const [horizon, setHorizon] = useState("week");
  const [channel, setChannel] = useState("seo");
  const [q, setQ] = useState("");

  const rows = useMemo(() => {
    const all = data?.focus[horizon]?.[channel] ?? [];
    const needle = q.trim().toLowerCase();
    return needle
      ? all.filter((r) => r.keyword.toLowerCase().includes(needle)
          || (r.en ?? "").toLowerCase().includes(needle))
      : all;
  }, [data, horizon, channel, q]);
  if (!data) return null;

  const horizons = data.meta.horizons.length ? data.meta.horizons : ["week"];
  const meta = CHANNEL_LABEL[channel];

  return (
    <>
      <SectionHead eyebrow="Focus queries" title="What to optimize for"
        note="Ranked by predicted growth in attention across all sources — including the bank's own Search Console history. Priority is a percentile: 100 = strongest signal today." />

      <div className="mb-3 flex flex-wrap items-center gap-2" role="tablist" aria-label="Horizon">
        {horizons.map((h) => (
          <button key={h} role="tab" aria-selected={h === horizon} onClick={() => setHorizon(h)}
            className={`min-h-11 cursor-pointer rounded-full border px-4.5 text-[13.5px] font-semibold transition-colors ${press} ${
              h === horizon ? "border-accent bg-accent text-white" : "border-line bg-surface text-ink2 hover:bg-surface2"}`}>
            {HORIZON_LABEL[h] ?? h}
          </button>
        ))}
        <span className="mx-1 hidden h-6 w-px bg-line sm:block" aria-hidden />
        {data.meta.channels.map((c) => (
          <button key={c} onClick={() => setChannel(c)} aria-pressed={c === channel}
            className={`min-h-11 cursor-pointer rounded-full border px-4.5 text-[13.5px] font-semibold transition-colors ${press} ${
              c === channel ? "border-accent bg-accent text-white" : "border-line bg-surface text-ink2 hover:bg-surface2"}`}>
            {CHANNEL_LABEL[c]?.name ?? c.toUpperCase()}
          </button>
        ))}
        <label className="relative ml-auto block w-full sm:w-56">
          <Search size={15} aria-hidden className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-ink2" />
          <span className="sr-only">Filter queries</span>
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Filter queries…"
            className="min-h-11 w-full rounded-full border border-line bg-surface pl-9 pr-4 text-[13.5px] outline-none placeholder:text-ink2/70 focus:border-accent" />
        </label>
      </div>

      {/* Keyed on the tab pair so switching cross-fades the new panel in
          instead of hard-cutting (reduced-motion turns the fade off). */}
      <Card key={`${horizon}/${channel}`} className="fade-in">
        <div className="mb-3 flex items-baseline gap-2">
          <h3 className="text-[15px] font-bold">{meta?.name}</h3>
          <span className="text-xs text-ink2">{meta?.sub}</span>
        </div>
        <p className="mb-3 text-[12.5px] text-ink2">{meta?.blurb}</p>
        {rows.length === 0 ? <Empty text={q ? "No queries match the filter." : "No signals yet — check back tomorrow."} /> : (
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-[13.5px]">
              <caption className="sr-only">Focus queries, {HORIZON_LABEL[horizon]}, {meta?.name}</caption>
              <thead>
                <tr className="border-b border-line text-left text-[11.5px] uppercase tracking-wide text-ink2">
                  <th className="py-2 pr-3 font-semibold">#</th>
                  <th className="py-2 pr-3 font-semibold">Query / topic</th>
                  <th className="py-2 pr-3 font-semibold">Priority</th>
                  <th className="py-2 font-semibold">Momentum</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r, i) => (
                  <tr key={r.keyword} className="border-b border-linesoft last:border-0">
                    <td className="tnum py-2.5 pr-3 text-ink2">{i + 1}</td>
                    <td className="py-2.5 pr-3">
                      <span dir="auto">{r.keyword}</span>{" "}
                      {r.competitor && <Badge tone="comp" title="Competitor-branded territory: contest with comparison content, not a dedicated page">competitor</Badge>}
                      {r.en && <div className="mt-0.5 text-[12px] italic text-ink2">"{r.en}"</div>}
                    </td>
                    <td className="py-2.5 pr-3">
                      <span className="mr-2 inline-block h-2 rounded-full bg-you align-middle" style={{ width: Math.max(r.score, 3) * 0.5 }} aria-hidden />
                      <span className="tnum">{Math.round(r.score)}</span>
                    </td>
                    <td className="py-2.5"><MomentumBadge delta={r.delta} velocity={r.velocity} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </>
  );
}
