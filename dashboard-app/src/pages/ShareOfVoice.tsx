import { useData } from "../lib/data";
import { BarRow, Card, Empty, SectionHead, SplitLegend } from "../components/ui";
import { Monogram } from "../components/icons";

export default function ShareOfVoice() {
  const { data } = useData();
  if (!data) return null;
  const rows = data.shareOfVoice;
  const max = Math.max(...rows.map((r) => r.ai + r.community), 1);
  const total = rows.reduce((s, r) => s + r.ai + r.community, 0) || 1;

  return (
    <>
      <SectionHead eyebrow="The conversation" title="Who owns the banking conversation?"
        note="Every time a bank is named in an AI-assistant answer (ChatGPT, Gemini, Perplexity, AI Overviews) or in community chatter (Reddit, news) over the last 7 days. Each sighting counts once — hover a segment for the split." />
      {rows.length === 0 ? <Card><Empty text="No mentions collected yet — check back after the next daily run." /></Card> : (
        <>
          <Card>
            <SplitLegend />
            {rows.map((r) => (
              <BarRow key={r.entity} name={r.entity} ai={r.ai} community={r.community}
                total={r.ai + r.community} max={max} you={r.kind === "brand"}
                icon={<Monogram name={r.entity} you={r.kind === "brand"} />} />
            ))}
          </Card>
          <Card className="mt-4 overflow-x-auto">
            <table className="w-full border-collapse text-[13.5px]">
              <caption className="sr-only">Share of voice by bank</caption>
              <thead>
                <tr className="border-b border-line text-left text-[11.5px] uppercase tracking-wide text-ink2">
                  <th className="py-2 pr-3 font-semibold">Bank</th>
                  <th className="py-2 pr-3 font-semibold">AI answers</th>
                  <th className="py-2 pr-3 font-semibold">Community</th>
                  <th className="py-2 pr-3 font-semibold">Total</th>
                  <th className="py-2 font-semibold">Share</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.entity} className={`border-b border-linesoft last:border-0 ${r.kind === "brand" ? "font-semibold" : ""}`}>
                    <td className="py-2 pr-3">
                      <span className="flex items-center gap-2">
                        <Monogram name={r.entity} you={r.kind === "brand"} size={18} />
                        {r.entity}
                      </span>
                    </td>
                    <td className="tnum py-2 pr-3">{r.ai.toLocaleString()}</td>
                    <td className="tnum py-2 pr-3">{r.community.toLocaleString()}</td>
                    <td className="tnum py-2 pr-3">{(r.ai + r.community).toLocaleString()}</td>
                    <td className="tnum py-2">{(100 * (r.ai + r.community) / total).toFixed(1)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        </>
      )}
    </>
  );
}
