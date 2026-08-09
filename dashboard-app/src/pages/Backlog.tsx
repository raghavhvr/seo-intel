import { useData } from "../lib/data";
import { Card, Empty, Reveal, SectionHead } from "../components/ui";
import { FileText } from "lucide-react";

export default function Backlog() {
  const { data } = useData();
  if (!data) return null;

  return (
    <>
      <SectionHead eyebrow="Content backlog" title="Publish these next — the citation gaps"
        note="Real questions people asked AI assistants where the answer cited other banks but never adcb.com. A clear, citable page for each is the fastest way into those answers: direct answer up top, rates/comparison table, FAQ schema." />
      {data.gaps.length === 0 ? <Card><Empty text="No open gaps — nothing is being ceded to competitors right now." /></Card> : (
        <Reveal className="grid grid-cols-1 gap-3.5 lg:grid-cols-2">
          {data.gaps.map((g, i) => (
            <Card key={i} className="flex gap-3.5">
              <div className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-accent/10 text-accent">
                <FileText size={17} aria-hidden />
              </div>
              <div className="min-w-0">
                <div className="text-[14.5px] font-bold leading-snug">{g.prompt}</div>
                <div className="mt-1.5 text-[12.5px] leading-relaxed text-ink2">
                  currently cited: {g.domains.join(", ")}
                </div>
                <div className="mt-0.5 text-[12px] text-ink2">asked on {g.models.join(", ")}</div>
              </div>
            </Card>
          ))}
        </Reveal>
      )}
    </>
  );
}
