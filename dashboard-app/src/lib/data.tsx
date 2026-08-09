import { createContext, useContext, useEffect, useState } from "react";

export interface FocusRow {
  keyword: string;
  score: number;
  delta: number;
  velocity: number;
  competitor: boolean;
  channels: string[];
  en?: string;
}
export interface Payload {
  meta: {
    project: string; market: string; generated: string; scoreDate: string | null;
    horizons: string[]; channels: string[]; modelMae: Record<string, number>;
  };
  kpis: {
    shareOfVoice: number | null; sovRank: number | null; citationShare: number | null;
    citationLeader: { domain: string; share: number; own: boolean } | null;
    keywordsTracked: number; openGaps: number;
  };
  shareOfVoice: { entity: string; kind: string; ai: number; community: number }[];
  citations: { domain: string; count: number; share: number; role: string }[];
  gaps: { prompt: string; promptEn?: string | null; domains: string[]; models: string[] }[];
  focus: Record<string, Record<string, FocusRow[]>>;
  evidence: Record<string, string[]>;
  events: {
    name: string; start: string; end: string | null; expected: boolean;
    regions: string[]; action: string; keywords: string[];
    daysUntil: number; prepNow: boolean; active: boolean;
  }[];
}

const Ctx = createContext<{ data: Payload | null; error: string | null }>({
  data: null, error: null,
});

export function DataProvider({ children }: { children: React.ReactNode }) {
  const [data, setData] = useState<Payload | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    fetch("./data.json")
      .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
      .then(setData)
      .catch((e) => setError(String(e)));
  }, []);
  return <Ctx.Provider value={{ data, error }}>{children}</Ctx.Provider>;
}

export const useData = () => useContext(Ctx);

export const HORIZON_LABEL: Record<string, string> = {
  week: "This week", month: "This month", quarter: "This quarter",
};
export const CHANNEL_LABEL: Record<string, { name: string; sub: string; blurb: string }> = {
  seo: { name: "SEO", sub: "Classic search",
    blurb: "Queries people type into Google. Create or refresh pages for the top ones." },
  aeo: { name: "AEO", sub: "Answer engines",
    blurb: "Question-style queries. Add a 40–60 word direct answer + FAQ schema to win featured snippets and voice." },
  geo: { name: "GEO", sub: "AI assistants",
    blurb: "Topics where ChatGPT, Gemini and AI Overviews shape the story. Publish citable explainers so AI engines reference the bank." },
};
