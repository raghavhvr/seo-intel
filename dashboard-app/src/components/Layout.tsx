import { NavLink, Outlet } from "react-router-dom";
import { useData } from "../lib/data";
import { press } from "./ui";
import {
  LayoutDashboard, Megaphone, Quote, Target, ListChecks, CalendarDays, Menu,
} from "lucide-react";
import { useEffect, useState } from "react";

const NAV = [
  { to: "/", label: "Overview", icon: LayoutDashboard, end: true },
  { to: "/share-of-voice", label: "Share of voice", icon: Megaphone },
  { to: "/citations", label: "AI citations", icon: Quote },
  { to: "/focus", label: "Focus queries", icon: Target },
  { to: "/backlog", label: "Content backlog", icon: ListChecks },
  { to: "/calendar", label: "Calendar", icon: CalendarDays },
];

export default function Layout() {
  const { data, error } = useData();
  const [open, setOpen] = useState(false);
  const generated = data ? new Date(data.meta.generated) : null;

  // Wayfinding: Escape is always a way out of the drawer.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  return (
    <div className="flex min-h-dvh">
      {/* The drawer enters from the left and must exit the same way — it stays
          mounted so both directions travel the same path. */}
      <aside className={`fixed inset-y-0 left-0 z-40 flex w-60 shrink-0 flex-col text-white transition-[transform,visibility] duration-300 ease-[cubic-bezier(0.22,1,0.36,1)] lg:static lg:visible lg:translate-x-0 ${open ? "visible translate-x-0" : "invisible -translate-x-full"}`}
        style={{ background: "linear-gradient(170deg, var(--hero-a), var(--hero-b))" }}>
        <div className="px-5 pb-4 pt-6">
          <div className="text-[17px] font-bold tracking-tight">TrendPulse</div>
          <div className="mt-0.5 text-[11.5px] text-white/60">ADCB · Search &amp; AI intelligence</div>
        </div>
        <nav className="flex-1 space-y-1 px-3" aria-label="Main">
          {NAV.map(({ to, label, icon: Icon, end }) => (
            <NavLink key={to} to={to} end={end} onClick={() => setOpen(false)}
              className={({ isActive }) =>
                `flex min-h-11 items-center gap-3 rounded-lg px-3 text-[13.5px] font-medium transition-colors ${press} ${
                  isActive ? "bg-white/15 text-white" : "text-white/70 hover:bg-white/8 hover:text-white"}`}>
              <Icon size={17} strokeWidth={2} aria-hidden />
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="px-5 py-5 text-[11px] leading-relaxed text-white/50">
          {generated && <>
            <span className="mr-1.5 inline-block h-1.5 w-1.5 rounded-full bg-emerald-400 align-middle" />
            Updates daily · {generated.toLocaleDateString("en-GB", { day: "numeric", month: "short" })}{" "}
            {generated.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })} UTC
          </>}
        </div>
      </aside>
      <div className={`fixed inset-0 z-30 bg-black/50 transition-opacity duration-300 lg:hidden ${open ? "opacity-100" : "pointer-events-none opacity-0"}`}
        onClick={() => setOpen(false)} aria-hidden />

      <div className="min-w-0 flex-1">
        <header className="chrome sticky top-0 z-20 flex min-h-13 items-center gap-3 px-4 lg:hidden">
          <button onClick={() => setOpen(true)} aria-label="Open navigation" aria-expanded={open}
            className={`grid h-11 w-11 cursor-pointer place-items-center rounded-lg hover:bg-surface2 ${press}`}>
            <Menu size={20} />
          </button>
          <span className="text-[15px] font-bold">TrendPulse</span>
        </header>
        <main className="mx-auto max-w-6xl px-4 pb-16 pt-6 sm:px-6" id="main">
          {error && (
            <div className="rounded-xl border border-warn/30 bg-warn/10 p-4 text-[13.5px]">
              Couldn't load data ({error}). The daily pipeline may not have published
              <code className="mx-1">data.json</code> yet — try again after the next run.
            </div>
          )}
          {!data && !error && (
            <div className="space-y-4" aria-busy="true" aria-label="Loading">
              {[0, 1, 2].map((i) => (
                <div key={i} className="h-28 animate-pulse rounded-2xl bg-surface2" />
              ))}
            </div>
          )}
          {data && <Outlet />}
        </main>
      </div>
    </div>
  );
}
