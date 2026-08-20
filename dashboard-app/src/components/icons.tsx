import { useState } from "react";
import { GLYPHS, MODEL_GLYPH } from "./glyphs";

/** Official mark for an AI engine (ChatGPT, Gemini, …). Falls back to
 *  nothing for engines we have no glyph for — the text label always stays. */
export function ModelIcon({ model, size = 13 }: { model: string; size?: number }) {
  const glyph = GLYPHS[MODEL_GLYPH[model] ?? ""];
  if (!glyph) return null;
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden
      className="inline-block align-[-2px]" fill={glyph.fill}>
      <path d={glyph.d} />
    </svg>
  );
}

/** Named brand glyph (e.g. "reddit", "googlenews") for source credits. */
export function SourceIcon({ name, size = 13 }: { name: string; size?: number }) {
  const glyph = GLYPHS[name];
  if (!glyph) return null;
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden
      className="inline-block align-[-2px]" fill={glyph.fill}>
      <path d={glyph.d} />
    </svg>
  );
}

/* Bank logos are wordmarks — unreadable at 18px, and only a couple exist as
   clean SVGs — so entities get consistent monogram chips instead. The brand
   keeps its blue; competitors cycle muted tones from the validated palette. */
const CHIP_TONES = ["#8a8984", "#6f7d8f", "#8a7d6a", "#7a8a76", "#87788a"];

function initials(name: string): string {
  const words = name.split(/\s+/).filter(Boolean);
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
  return (words[0][0] + words[words.length - 1][0]).toUpperCase();
}

export function Monogram({ name, you = false, size = 20 }: {
  name: string; you?: boolean; size?: number;
}) {
  const hash = [...name].reduce((h, ch) => (h * 31 + ch.charCodeAt(0)) | 0, 7);
  const bg = you ? "var(--series-you)" : CHIP_TONES[Math.abs(hash) % CHIP_TONES.length];
  return (
    <span aria-hidden
      className="inline-flex shrink-0 items-center justify-center rounded-md font-bold text-white"
      style={{ width: size, height: size, background: bg, fontSize: size * 0.42 }}>
      {initials(name)}
    </span>
  );
}

/** Live favicon for a cited domain (Google's favicon service). The monogram
 *  chip renders underneath and the favicon fades in over it only once it has
 *  actually loaded — a slow, blocked, or missing favicon never leaves a gap. */
export function DomainIcon({ domain, size = 16 }: { domain: string; size?: number }) {
  const [loaded, setLoaded] = useState(false);
  return (
    <span className="relative inline-flex shrink-0" style={{ width: size, height: size }}>
      <Monogram name={domain} size={size} />
      <img src={`https://www.google.com/s2/favicons?domain=${encodeURIComponent(domain)}&sz=32`}
        width={size} height={size} alt="" loading="lazy"
        className={`absolute inset-0 rounded-[4px] ${loaded ? "" : "opacity-0"}`}
        onLoad={() => setLoaded(true)} />
    </span>
  );
}

/** The TrendPulse mark: a pulse line on navy, brass beat. Used in the
 *  sidebar and (as a data URI) the favicon. */
export function Mark({ size = 26 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden className="shrink-0">
      <rect width="32" height="32" rx="8" fill="#17345a" />
      <path d="M5 19h6l3-9 5 13 3-7h5" fill="none" stroke="#c9a961"
        strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
