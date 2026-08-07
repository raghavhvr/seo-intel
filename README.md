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
| Google Trends (`pytrends`) | Search interest 0–100 **per country** + rising related queries, 90-day daily backfill | SEO | Daily | None | Unofficial API; rate-limited (collector backs off gracefully) |
| Google Autocomplete | Real query suggestions **per country × language** (EN + AR modifiers) | SEO, AEO | Real-time | None | Unofficial endpoint (`suggestqueries.google.com`) |
| Wikimedia Pageviews | Official, open API; daily article views per language edition (en + ar), 60-day backfill | SEO, GEO | Daily | None | Most reliable source here; no per-country filter |
| Hacker News (Algolia API) | Official search API; story counts + front page | GEO | Real-time | None | Best early-warning for AI/dev topics |
| Stack Exchange API | Official; question volume + hot questions (`money`, `webmasters`) | AEO | Real-time | None (optional key raises quota) | Literally the questions people want answered |
| Reddit | Rising threads & questions in UAE/GCC + money/AI subreddits | AEO, GEO | Real-time | Optional free OAuth (`REDDIT_CLIENT_ID/SECRET`) — public JSON otherwise | Set the env vars for reliability |
| Google News RSS | Article velocity per keyword **per country × language** (AE:en, AE:ar, …) | SEO | Real-time | None | News velocity often leads search demand |
| arXiv API | Official, open; new-paper velocity per topic | GEO | Daily | None | Research chatter → AI answers weeks later |
| Hugging Face Hub API | Official, open; trending models & model counts per topic | GEO | Real-time | None | Shows which AI capabilities/jargon are gaining traction |

**First-party and GEO data (already wired in):**

- **GSC / GA4 data dumps** — drop exports into `data_imports/gsc/` and `data_imports/ga4/` (CSV or Excel; dated rows or aggregate exports — the importer detects columns and attributes aggregate rows to the export window in the filename). GSC impressions/clicks = ground-truth demand; GA4 organic sessions per landing page = satisfied demand (slugs become topic keywords). `python -m trendpulse import`, or automatic as the first step of `run-daily`. The directory is git-ignored — it's private first-party data.
- **TryProfound (GEO ground truth)** — with `PROFOUND_API_KEY` set (Enterprise plan), the collector pulls the *Banking & Finance* category daily: per-asset **AI share-of-voice / visibility** (ADCB vs Emirates NBD, FAB, …), **raw prompt answers** (the actual questions AI engines field, with mentions per model — premium AEO/GEO targeting material), and **cited URLs** (which pages LLMs cite, so you can model the format that earns citations). The report gains a **Brand share of voice** section; community chatter mentions (Reddit/news/HN) are merged in with alias-aware matching (FAB ≠ "fabulous").

**Still free, still optional later:** YouTube Data API (free key) for video velocity; Common Crawl (open, monthly) for corpus shifts; a self-hosted LLM probe (Ollama) as a Profound complement.

Paid-only gaps to be aware of: true SERP rank/People-Also-Ask at scale (SerpAPI, DataForSEO) and keyword search-volume tooling (Ahrefs/Semrush). The tool is designed to work without them; they plug in as extra collectors if you later want them.

---

## Architecture

```
 config.yaml (seeds, entities, sources, horizons)
        │
        ▼
 collectors/  ── 9 free APIs ──►  observations + discoveries
        │                              │ SQLite (data/trendpulse.db)
        ▼                              ▼
 features.py   blended attention = mean of per-source z-scores
        │      + velocity / momentum / breadth / calendar features
        ▼
 model.py      HistGradientBoosting per horizon (7/30/90d)
        │      self-supervised labels from future attention,
        │      time-split holdout MAE logged to model_runs
        ▼
 report.py     reports/YYYY-MM-DD.md + latest.md + per-channel CSVs
        │      ranked focus lists for week / month / quarter × SEO / AEO / GEO
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

Individual stages: `python -m trendpulse import` (GSC/GA4 dumps) / `ingest` / `train` / `report`. Add `-v` for debug logs. Repo secrets for CI: `PROFOUND_API_KEY` (GEO visibility), optionally `REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET`.

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

- `pytrends` and the autocomplete endpoint are unofficial Google APIs — respect rate limits and expect occasional 429s (handled, with gaps in that source only).
- Reddit's public JSON endpoints rate-limit aggressively; set `REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET` (free "script" app) as repo secrets for reliable runs.
- Scores are directional decision-support, not traffic forecasts. Validate big bets against Search Console before committing serious resources.
- Check each source's terms of service for your usage volume.

## Development

```bash
pip install -e .[dev]
pytest
```
