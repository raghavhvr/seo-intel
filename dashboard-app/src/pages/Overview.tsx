import { Link } from "react-router-dom";
import { useData, CHANNEL_LABEL, FocusRow } from "../lib/data";
import { Badge, BarRow, Card, CountUp, MomentumBadge, Reveal, SectionHead, SplitLegend } from "../components/ui";
import { ArrowRight } from "lucide-react";

export default function Overview() {
  const { data } = useData();
  if (!data) return null;
  const { kpis, meta } = data;

  // Best non-competitor week picks across channels, deduped by keyword.
  const best = new Map<string, FocusRow>();
  for (const ch of meta.channels) {
    for (const row of (data.focus.week?.[ch] ?? []).slice(0, 6)) {
      if (row.competitor) continue;
      const prev = best.get(row.keyword);
      if (!prev || row.score > prev.score) best.set(row.keyword, row);
    }
  }
  const picks = [...best.values()].sort((a, b) => b.score - a.score).slice(0, 3);
  const sov = data.shareOfVoice.slice(0, 6);
  const sovMax = Math.max(...sov.map((r) => r.ai + r.community), 1);

  return (
    <>
      <h1 className="display text-[28px] font-semibold">{meta.project}</h1>
      <p className="mt-1 text-[13px] text-ink2">{meta.market} · data through {meta.scoreDate ?? "—"}</p>

      <Reveal className="mt-5 grid grid-cols-1 gap-3.5 sm:grid-cols-2 xl:grid-cols-4">
        <Card>
          <div className="tnum text-[32px] font-semibold tracking-[-0.02em]">
            {kpis.shareOfVoice != null ? <><CountUp value={kpis.shareOfVoice} /><span className="text-base font-semibold text-ink2">%</span></> : "—"}
          </div>
          <div className="mt-1 text-[12.5px] leading-snug text-ink2">share of voice when AI assistants &amp; communities discuss UAE banks (7 days)</div>
          {kpis.sovRank && <div className="mt-2 text-xs font-semibold text-ink2">#{kpis.sovRank} of the tracked banks</div>}
        </Card>
        <Card>
          <div className="tnum text-[32px] font-semibold tracking-[-0.02em]">
            {kpis.citationShare != null ? <><CountUp value={kpis.citationShare} /><span className="text-base font-semibold text-ink2">%</span></> : "—"}
          </div>
          <div className="mt-1 text-[12.5px] leading-snug text-ink2">of AI-engine citations for banking prompts go to adcb.com (30 days)</div>
          {kpis.citationLeader && !kpis.citationLeader.own && (
            <div className="mt-2 text-xs font-semibold text-warn">leader: {kpis.citationLeader.domain} at {kpis.citationLeader.share}%</div>
          )}
        </Card>
        <Card>
          <div className="tnum text-[32px] font-semibold tracking-[-0.02em]"><CountUp value={kpis.keywordsTracked} /></div>
          <div className="mt-1 text-[12.5px] leading-snug text-ink2">queries &amp; topics tracked and re-scored every morning</div>
        </Card>
        <Card>
          <div className="tnum text-[32px] font-semibold tracking-[-0.02em]"><CountUp value={kpis.openGaps} /></div>
          <div className="mt-1 text-[12.5px] leading-snug text-ink2">AI questions currently answered with competitor sources</div>
          <Link to="/backlog" className="mt-2 inline-flex items-center gap-1 text-xs font-semibold text-accent hover:underline">
            see the backlog <ArrowRight size={13} aria-hidden />
          </Link>
        </Card>
      </Reveal>

      <SectionHead eyebrow="Start here" title="This week's top opportunities"
        note="The strongest signals right now, with the evidence behind them and the play to run." />
      <Reveal className="grid grid-cols-1 gap-3.5 md:grid-cols-3">
        {picks.map((p) => (
          <Card key={p.keyword} className="border-l-[3px] border-l-brass">
            <div className="mb-1.5 flex flex-wrap gap-1.5">
              {p.channels.map((c) => <Badge key={c} tone="chip">{CHANNEL_LABEL[c]?.name ?? c.toUpperCase()}</Badge>)}
              <MomentumBadge delta={p.delta} velocity={p.velocity} />
            </div>
            <div className="text-[15.5px] font-bold leading-snug" dir="auto">{p.keyword}</div>
            {p.en && <div className="text-[12.5px] italic text-ink2">"{p.en}"</div>}
            <div className="mt-2 text-[13px] leading-relaxed text-ink2">
              {p.channels.includes("geo")
                ? "Publish a definitive, citable explainer so AI engines reference the bank."
                : p.channels.includes("aeo")
                  ? "Add a 40–60 word direct answer + FAQ schema; target snippets and voice."
                  : "Create or refresh a dedicated page targeting this query; interlink from related pages."}
            </div>
            {(data.evidence[p.keyword] ?? []).length > 0 && (
              <div className="mt-2.5 border-t border-linesoft pt-2 text-[12px] leading-relaxed text-ink2">
                Seen in: {data.evidence[p.keyword].join(" · ")}
              </div>
            )}
          </Card>
        ))}
      </Reveal>

      <SectionHead eyebrow="The conversation" title="Who owns the banking conversation?"
        note="Bank mentions across AI-assistant answers and community chatter, last 7 days. Each sighting counts once." />
      <Card>
        <SplitLegend />
        {sov.map((r) => (
          <BarRow key={r.entity} name={r.entity} ai={r.ai} community={r.community}
            total={r.ai + r.community} max={sovMax} you={r.kind === "brand"} />
        ))}
        <Link to="/share-of-voice" className="mt-3 inline-flex items-center gap-1 text-[13px] font-semibold text-accent hover:underline">
          full share-of-voice view <ArrowRight size={14} aria-hidden />
        </Link>
      </Card>
    </>
  );
}
