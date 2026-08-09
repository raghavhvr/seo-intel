import { useData } from "../lib/data";
import { BarRow, Card, Empty, SectionHead } from "../components/ui";

export default function Citations() {
  const { data } = useData();
  if (!data) return null;
  const rows = data.citations;
  const max = Math.max(...rows.map((r) => r.count), 1);

  return (
    <>
      <SectionHead eyebrow="Inside AI answers" title="Who do AI engines cite for banking questions?"
        note="The websites AI assistants link as sources when answering banking & finance prompts (last 30 days). More citations → more presence inside the answers customers actually read." />
      {rows.length === 0 ? <Card><Empty text="No citation data yet." /></Card> : (
        <Card>
          {rows.map((r) => (
            <BarRow key={r.domain} name={r.domain} total={r.count} max={max}
              you={r.role === "own"} />
          ))}
          <p className="mt-3 border-t border-linesoft pt-3 text-[12.5px] text-ink2">
            Closing the gap: the <a href="#/backlog" className="font-semibold text-accent hover:underline">content backlog</a> lists
            the exact prompts where competitors get cited and adcb.com doesn't.
          </p>
        </Card>
      )}
    </>
  );
}
