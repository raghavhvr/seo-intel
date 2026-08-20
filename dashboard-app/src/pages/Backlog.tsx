import { useData } from "../lib/data";
import { Card, Empty, Reveal, SectionHead } from "../components/ui";
import { DomainIcon, ModelIcon } from "../components/icons";
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
                <div className="text-[14.5px] font-bold leading-snug" dir="auto">{g.prompt}</div>
                {g.promptEn && <div className="mt-0.5 text-[12.5px] italic text-ink2">"{g.promptEn}"</div>}
                <div className="mt-2 flex flex-wrap items-center gap-x-2.5 gap-y-1 text-[12.5px] leading-relaxed text-ink2">
                  <span>currently cited:</span>
                  {g.domains.map((d) => (
                    <span key={d} className="inline-flex items-center gap-1">
                      <DomainIcon domain={d} size={13} />{d}
                    </span>
                  ))}
                </div>
                <div className="mt-1 flex flex-wrap items-center gap-x-2.5 gap-y-1 text-[12px] text-ink2">
                  <span>asked on</span>
                  {g.models.map((m) => (
                    <span key={m} className="inline-flex items-center gap-1">
                      <ModelIcon model={m} size={12} />{m}
                    </span>
                  ))}
                </div>
              </div>
            </Card>
          ))}
        </Reveal>
      )}
    </>
  );
}
