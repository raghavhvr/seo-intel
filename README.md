# TrendPulse

**Trend spotting for SEO, AEO and GEO teams — configured for a UAE-first GCC & Levant banking client (ADCB profile).** TrendPulse pulls fresh data every day from free, open APIs, continuously trains a trend model on your accumulated history, and outputs a ranked list of **queries and keywords to focus on this week, this month and this quarter** — split by channel:

| Channel | What it optimizes for | Signal flavour |
|---------|----------------------|----------------|
| **SEO** | Classic search demand (Google/Bing) | Rising search interest, news velocity, commercial modifiers |
| **AEO** | Answer engines, featured snippets, voice | Question-format queries ("how to…", "what is…", "cost of…") from autocomplete, Stack Exchange, Reddit |
| **GEO** | Generative engines (ChatGPT, Perplexity, Gemini, AI Overviews) citing your brand | AI-topic momentum on Hacker News, arXiv, Hugging Face, Reddit AI communities |

## Regional focus: UAE, GCC & Levant (banking client)

The shipped `config.yaml` is tuned for a UAE bank (ADCB profile) — retarget by editing one file:

- **Countries**: `regions: [AE, SA, QA, KW, BH, OM, JO, LB]` (UAE first = primary). Google Trends interest, autocomplete suggestions and Google News velocity are collected **per country** and stored with a region tag, so a query breaking out in KSA but flat in the UAE is visible as such (cross-country confirmation feeds the breadth feature).
- **Bilingual EN + AR**: `languages: [en, ar]`. Arabic seeds are included out of the box (e.g. قرض شخصي الإمارات, التمويل العقاري الإمارات); normalization handles Arabic script and strips tashkeel, Arabic question words (كيف، هل، ما، …) feed the AEO channel, and Wikipedia pageviews are pulled from both `en.wikipedia` and `ar.wikipedia`.
- **Banking universe**: retail-banking seeds (cards, personal/auto loans, mortgages, savings, remittances, Islamic banking, business banking), AEO money questions, and GEO topics (digital banks, Digital Dirham/CBDC, open banking, BNPL, fintech) — plus a competitor entity set (Emirates NBD, FAB, DIB, Mashreq, RAKBANK, CBD, HSBC UAE, Wio, Liv) for share-of-voice tracking.
- **GCC seasonal calendar** (`seasonal_events`): Ramadan, Eid Al Fitr, Eid Al Adha (expected dates — Hijri shifts; verify before publishing), Dubai Shopping Festival, UAE/Saudi National Days, GITEX, back-to-school. Each event carries prep lead-time and keyword angles; the report shows an **"Upcoming regional moments"** section and the pipeline auto-injects event keywords into the tracked universe when the prep window opens — banking content must rank *before* the moment, not during it.
- **Relevance gate**: broad global feeds (HN front page, HF trending) are only folded into the tracked universe when they share vocabulary with it, are question-shaped, or are GEO-relevant — regional noise stays out of a banking client's focus list.
- Regional community signals come from r/dubai, r/abudhabi, r/UAE, r/saudiarabia, r/qatar plus global money subs, and `money.stackexchange.com` for AEO questions.

Known limits: Wikipedia pageviews are per-edition, not per-country (the API has no geo filter); Reddit/StackExchange/HN are global English-heavy communities — the UAE-specificity there comes from the subreddit/keyword mix.

---

## Your questions, answered

### 1. What is required?

Five components, all in this repo:

1. **Seed universe** — your topics per channel (`config.yaml`). ~20–50 seeds is a good start; the tool expands it automatically by harvesting rising related queries, autocomplete suggestions, hot questions and headlines every day.
2. **Data ingestion** — collectors that normalize every source into `(date, keyword, source, metric, value)` observations plus keyword *discoveries*.
3. **Storage** — a local SQLite database (`data/trendpulse.db`). No server needed; it lives in the repo so the CI job keeps history across runs.
4. **Model** — per-horizon (7/30/90-day) gradient-boosting models that predict the change in a keyword's blended cross-source attention. Labels are **self-supervised** (computed from data already collected: "what did attention do in the N days after date t?"), so the model genuinely re-learns from every new day of data with zero manual labelling. Until enough history exists (~200 labelled samples — reachable in week one thanks to 60–90 days of backfill from Google Trends and Wikipedia), a statistical momentum/breakout scorer is used instead.
5. **Scheduling & reporting** — a daily GitHub Action (`.github/workflows/daily.yml`) runs `ingest → train → report` and commits the fresh data, models and a markdown + CSV report to the repo.

Inputs needed from the SEO team: the seed topics, brand/competitor entity names, and (optionally) target region/language. Everything else is automated.

### 2. Can it be built with open-source / free APIs that stay current?

**Yes.** Every collector below is free and updates in real time or daily:

| Source | Provides | Channel(s) | Cadence | Auth | Notes |
|--------|----------|-----------|---------|------|-------|
| Google Trends (`pytrends`) | Search interest 0–100 **per country** + rising related queries, 90-day daily backfill | SEO | Daily | None | Unofficial, aggressively rate-limited → primary region daily + remaining regions rotate (`regions_per_run`), 60s back-off on 429 |
| Google Autocomplete | Real query suggestions **per country × language** (EN + AR modifiers) | SEO, AEO | Real-time | None | Unofficial endpoint (`suggestqueries.google.com`); highest-relevance discovery source in audits |
| Wikimedia Pageviews | Official, open API; daily article views per language edition (en + ar), 60-day backfill | SEO, GEO | Daily | None | Most reliable source here; no per-country filter |
| Hacker News (Algolia API) | Official search API; story counts + front page | GEO | Real-time | None | Global tech community — auto-gated to GEO-relevant keywords only |
| Stack Exchange API | Official; question volume (30d, core terms) + hot questions (`money`, `webmasters`) | AEO | Real-time | None (optional key raises quota) | Post-2024 cadence is low — weekly counts are sparse; hot-question mining is the real value |
| Reddit via [Arctic Shift](https://arctic-shift.photon-reddit.com) | Mention counts + threads in UAE/GCC + money subreddits | AEO, GEO | Daily archive | None | No Reddit API access needed. One bulk pull per subreddit + local keyword/entity matching (word-boundary safe); paced for its rate limits |
| Google News RSS | Article velocity per keyword **per country × language** (AE:en, AE:ar, …) | SEO | Real-time | None | News velocity often leads search demand |
| arXiv API | Official, open; new-paper velocity per topic | GEO | Daily | None | Auto-gated to GEO-relevant keywords |
| Hugging Face Hub API | Official, open; trending models & model counts per topic | GEO | Real-time | None | Auto-gated to GEO-relevant keywords |
| NASA EONET | Natural events (floods, storms, dust, earthquakes) mapped to banking demand | SEO, AEO | Near-real-time | None | Gulf floods → insurance-claim queries; disasters in remittance corridors (India/Pakistan/Philippines) → money-transfer spikes. Client-side bbox filtering (server-side `bbox` leaks) + curated category→keyword mapping |

**First-party and GEO data (already wired in):**

- **GSC / GA4 data dumps** — drop exports into `data_imports/gsc/` and `data_imports/ga4/` (CSV or Excel; dated rows or aggregate exports — the importer detects columns and attributes aggregate rows to the export window in the filename). GSC impressions/clicks = ground-truth demand; GA4 organic sessions per landing page = satisfied demand (slugs become topic keywords). `python -m trendpulse import`, or automatic as the first step of `run-daily`. The directory is git-ignored — it's private first-party data.
- **TryProfound (GEO ground truth)** — with `PROFOUND_API_KEY` set (Enterprise plan), the collector pulls the *Banking & Finance* category daily: per-asset **AI share-of-voice / visibility** (ADCB vs Emirates NBD, FAB, …), **raw prompt answers** (the actual questions AI engines field, with mentions per model — premium AEO/GEO targeting material), and **cited URLs** stored as structured citation rows. The report gains **Brand share of voice** and **GEO citation gaps** sections; community chatter mentions (Reddit/news/HN) are merged in with alias-aware matching (FAB ≠ "fabulous").

**Delivery & alerts (built in):**

- **Morning briefing** to Slack and/or Teams (`SLACK_WEBHOOK_URL` / `TEAMS_WEBHOOK_URL` secrets): breakouts to act on now (velocity z ≥ `alerts.breakout_z`), top weekly focus queries, and ADCB's 7-day AI share of voice, with a link to the full report. Runs as the last step of `run-daily`; `python -m trendpulse notify` standalone. Missing webhooks skip silently.
- **GEO citation-gap analysis** — aggregates 30 days of Profound citations into a domain share table (you vs competitors vs others) and ranks **prompts where AI engines cite other domains but never adcb.com** — a ready-made GEO content backlog with per-prompt actions.

**Still free, still optional later:** YouTube Data API (free key) for video velocity; Common Crawl (open, monthly) for corpus shifts; a self-hosted LLM probe (Ollama) as a Profound complement; HTML dashboard on GitHub Pages.

Paid-only gaps to be aware of: true SERP rank/People-Also-Ask at scale (SerpAPI, DataForSEO) and keyword search-volume tooling (Ahrefs/Semrush). The tool is designed to work without them; they plug in as extra collectors if you later want them.

---

## Architecture

```
 config.yaml (seeds, entities, regions, sources, horizons, seasonal events)
        │
        ├── importers/   GSC + GA4 dumps (data_imports/, git-ignored)
        ├── collectors/  ── 9 free APIs ──►  observations + discoveries
        └── collectors/profound.py  ── TryProfound ──►  AI SOV, prompts, citations
        │                              │ SQLite (data/trendpulse.db) + entities table
        ▼                              ▼
 features.py   blended attention = mean of per-series z-scores
        │      (per source × metric × region × language)
        │      + velocity / momentum / breadth / calendar features
        ▼
 model.py      HistGradientBoosting per horizon (7/30/90d)
        │      self-supervised labels from future attention,
        │      time-split holdout MAE logged to model_runs
        ▼
 report.py     reports/YYYY-MM-DD.md + latest.md + per-channel CSVs
        │      week / month / quarter × SEO / AEO / GEO
        │      + upcoming regional moments + brand share of voice
        ▼
 .github/workflows/daily.yml   runs the loop every day, commits results
```

Why blended z-scores: pageviews (thousands), Trends interest (0–100) and mention counts (units) are incomparable raw, so each source series is z-scored against its own history before blending. A keyword that is hot on *several* sources at once scores highest — cross-source confirmation kills single-source noise.

## Quick start

```bash
pip install -r requirements.txt
cp config.example.yaml config.yaml   # shipped ready for the ADCB profile — edit as needed
python -m trendpulse demo            # offline end-to-end run on synthetic data
python -m trendpulse run-daily       # import dumps + live ingest + train + report
```

Individual stages: `python -m trendpulse import` (GSC/GA4 dumps) / `ingest` / `train` / `report` / `notify`. Add `-v` for debug logs.

### Secrets (never in the workflow file)

The workflow YAML contains **no key material** — only `${{ secrets.NAME }}` references that GitHub resolves at runtime. Values are encrypted at rest and masked in logs. Add them under **Settings → Environments → `trendpulse` → Environment secrets** (the workflow job is bound to that environment), or as repo-level Actions secrets — both resolve through the same `secrets.` context. Do **not** use the "Variables" tab for keys: variables are stored in plain text.

Needed: `PROFOUND_API_KEY` (GEO visibility), `SLACK_WEBHOOK_URL` and/or `TEAMS_WEBHOOK_URL` (briefing). Reddit needs nothing — Arctic Shift is a public archive API.

### Where do GSC/GA4 dumps go?

Short version: **dumps stay on your machine; only the extracted numbers travel.**

1. Drop exports into `data_imports/gsc/` and `data_imports/ga4/` locally. The directory is **git-ignored** — raw dumps are never uploaded to GitHub.
2. Run `python -m trendpulse import`. Each row is parsed into compact observations inside `data/trendpulse.db` (SQLite). This database **is the cache**: imports are idempotent upserts, so re-running or overlapping exports never duplicates data.
3. Commit the updated `data/trendpulse.db` (a few MB) — the daily workflow commits `data/` anyway, so history persists across CI runs.
4. Delete the dumps if you like; they're no longer needed. Refresh with a new export whenever convenient (monthly/quarterly is fine — rows carry their own dates).

## Continuous training

The daily GitHub Action (06:15 UTC, `.github/workflows/daily.yml`):

1. Pulls fresh data from all enabled sources.
2. Retrains every horizon model on *all* history collected so far and logs holdout MAE to the `model_runs` table — accuracy is auditable over time.
3. Regenerates the reports and commits `data/` + `reports/` back to the repo, so tomorrow's run starts from today's history.

After merging to your default branch the cron runs automatically. New keywords discovered today are tracked from tomorrow, and the model re-learns what actually grew every single day.

## Reading the report

- **Score** — percentile rank within the run (0–100), combining predicted momentum, current velocity and cross-source breadth.
- **Predicted momentum** — expected change in blended attention over the horizon (`rising` / `steady` / `cooling`).
- **Velocity (z)** — how hot the last 7 days are vs. the prior 28.
- **Signals** — `breakout` (latest point > 2σ above baseline — act now), `question` (AEO formatting), `ai-topic` (GEO formatting).
- **Deep dive** — top picks with evidence (the headlines/questions/queries that triggered them) and a suggested next action per channel.

## Extending

- **New source**: subclass `Collector` in `trendpulse/collectors/`, return `Observation`/`Discovery` objects, register it in `collectors/__init__.py`. Collectors must never raise — log and degrade gracefully so one flaky API never kills a daily run.
- **Slack/email delivery**: post `reports/latest.md` from the workflow.
- **Guardrails**: `keywords.max_universe` and `keywords.max_new_per_day` cap universe growth.

## Caveats

- `pytrends` and the autocomplete endpoint are unofficial Google APIs — expect 429s. Trends runs the primary region daily and rotates the rest (`google_trends.regions_per_run`), so full regional coverage accrues over the week rather than one throttled run.
- Reddit data comes from the Arctic Shift archive API (no official Reddit API needed). It rate-limits politely ("slow down" responses) — the collector paces requests and retries; scores reflect archive-time values, not live votes.
- Stack Exchange question volume is genuinely low post-2024 — treat it as an AEO question-mining source, not a velocity gauge.
- HN/arXiv/Hugging Face are global tech sources; they only track GEO-relevant keywords (banking terms there are noise by design).
- NASA EONET is quiet in the Gulf for months at a time — zero events is normal, and the collector contributes nothing until an event fires (then it injects the mapped keyword angles with the event as evidence).
- Scores are directional decision-support, not traffic forecasts. Validate big bets against Search Console before committing serious resources.
- Check each source's terms of service for your usage volume.

## Development

```bash
pip install -e .[dev]
pytest
```
