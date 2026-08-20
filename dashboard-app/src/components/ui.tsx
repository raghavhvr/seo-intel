import { useEffect, useRef } from "react";
import { animate, stagger, spring } from "animejs";

const reduced = () =>
  window.matchMedia("(prefers-reduced-motion: reduce)").matches;

/* Critically damped springs (Apple: damping 1.0), so motion settles without
   overshoot and settle time emerges from the physics, not a fixed timer.
   stiffness = (2π / response)², damping = 2·√stiffness. */
const settle = () => spring({ mass: 1, stiffness: 247, damping: 31.4 }); // response ≈ 0.4s
const settleSlow = () => spring({ mass: 1, stiffness: 110, damping: 21 }); // response ≈ 0.6s

/** Press feedback on pointer-down (not release) for anything tappable. */
export const press =
  "transition-transform duration-100 ease-out active:scale-[0.97]";

/** Staggered fade-up entrance for a container's direct children (35ms/item). */
export function Reveal({ children, className = "" }: {
  children: React.ReactNode; className?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el || reduced()) return;
    const kids = Array.from(el.children) as HTMLElement[];
    kids.forEach((k) => { k.style.opacity = "0"; });
    animate(kids, {
      opacity: [0, 1], translateY: [10, 0],
      delay: stagger(35), ease: settle(),
    });
  }, []);
  return <div ref={ref} className={className}>{children}</div>;
}

/** Animated count-up number (respects reduced motion). */
export function CountUp({ value, suffix = "" }: { value: number; suffix?: string }) {
  const ref = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const fmt = (v: number) =>
      (Number.isInteger(value) ? Math.round(v).toLocaleString() : v.toFixed(1)) + suffix;
    if (reduced()) { el.textContent = fmt(value); return; }
    const obj = { v: 0 };
    animate(obj, {
      v: value, ease: settleSlow(),
      onUpdate: () => { el.textContent = fmt(obj.v); },
    });
  }, [value, suffix]);
  return <span ref={ref} className="tnum" />;
}

export function Card({ children, className = "" }: {
  children: React.ReactNode; className?: string;
}) {
  return (
    <div className={`card rounded-2xl border border-line bg-surface p-5 ${className}`}>
      {children}
    </div>
  );
}

export function SectionHead({ eyebrow, title, note }: {
  eyebrow: string; title: string; note?: string;
}) {
  return (
    <div className="mt-11 mb-4">
      <div className="text-[11px] font-bold uppercase tracking-[0.14em] text-brass">{eyebrow}</div>
      <h2 className="display mt-0.5 text-[22px] font-semibold">{title}</h2>
      {note && <p className="mt-1 max-w-2xl text-[13.5px] leading-relaxed text-ink2">{note}</p>}
    </div>
  );
}

type BadgeTone = "you" | "hot" | "rising" | "cooling" | "comp" | "chip";
const TONES: Record<BadgeTone, string> = {
  you: "bg-you/15 text-accent",
  hot: "bg-warn/15 text-warn",
  rising: "bg-good/15 text-good",
  cooling: "bg-surface2 text-ink2",
  comp: "bg-warn/10 text-warn",
  chip: "bg-accent/10 text-accent",
};
export function Badge({ tone, children, title }: {
  tone: BadgeTone; children: React.ReactNode; title?: string;
}) {
  return (
    <span title={title}
      className={`inline-block whitespace-nowrap rounded-full px-2 py-0.5 text-[11px] font-semibold ${TONES[tone]}`}>
      {children}
    </span>
  );
}

export function MomentumBadge({ delta, velocity }: { delta: number; velocity: number }) {
  if (velocity >= 3) return <Badge tone="hot">act now</Badge>;
  if (delta > 0.15) return <Badge tone="rising">rising</Badge>;
  if (delta < -0.15) return <Badge tone="cooling">cooling</Badge>;
  return null;
}

/** Ranked bar with optional AI/community split. Animates width on mount. */
export function BarRow({ name, ai, community, total, max, you, unit = "" }: {
  name: string; ai?: number; community?: number; total: number;
  max: number; you: boolean; unit?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el || reduced()) return;
    const segs = Array.from(el.querySelectorAll<HTMLElement>("[data-w]"));
    segs.forEach((s, i) => {
      const target = s.dataset.w + "%";
      s.style.width = "0%";
      animate(s, { width: target, ease: settle(), delay: i * 40 });
    });
  }, []);
  const dark = you ? "var(--series-you)" : "var(--series-other)";
  const light = you ? "var(--series-you-2)" : "var(--series-other-2)";
  const hasSplit = ai !== undefined && community !== undefined;
  return (
    <div ref={ref} className="grid grid-cols-[140px_1fr_70px] items-center gap-3 py-1.5 sm:grid-cols-[190px_1fr_84px]">
      <div className={`truncate text-[13.5px] ${you ? "font-bold" : ""}`} title={name}>
        {name} {you && <Badge tone="you">you</Badge>}
      </div>
      <div className="flex h-4 rounded-[5px] bg-surface2" role="img"
        aria-label={`${name}: ${total.toLocaleString()}${unit}`}>
        {hasSplit ? (<>
          {ai! > 0 && <div data-w={(100 * ai!) / max} title={`${name} — ${ai!.toLocaleString()} AI-answer mentions`}
            className="h-4 rounded-l-[5px]" style={{ background: dark, width: `${(100 * ai!) / max}%` }} />}
          {community! > 0 && <div data-w={(100 * community!) / max} title={`${name} — ${community!.toLocaleString()} community mentions`}
            className="ml-0.5 h-4 rounded-r-[5px]" style={{ background: light, width: `${(100 * community!) / max}%` }} />}
        </>) : (
          <div data-w={Math.max((100 * total) / max, 1.5)} title={`${name} — ${total.toLocaleString()}${unit}`}
            className="h-4 rounded-[5px]" style={{ background: you ? dark : light, width: `${Math.max((100 * total) / max, 1.5)}%` }} />
        )}
      </div>
      <div className="tnum text-right text-[12.5px] text-ink2">{total.toLocaleString()}{unit}</div>
    </div>
  );
}

export function SplitLegend() {
  return (
    <div className="mb-3 flex gap-4 text-xs text-ink2">
      <span><i className="mr-1.5 inline-block h-2.5 w-2.5 rounded-[3px] align-[-1px]" style={{ background: "var(--series-you)" }} />AI-assistant answers</span>
      <span><i className="mr-1.5 inline-block h-2.5 w-2.5 rounded-[3px] align-[-1px]" style={{ background: "var(--series-you-2)" }} />Community &amp; news</span>
    </div>
  );
}

export function Empty({ text }: { text: string }) {
  return <p className="py-6 text-center text-[13px] text-ink2">{text}</p>;
}
