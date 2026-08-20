# Icon drop folder

Drop SVG files here and the app picks them up **by filename** at build time —
no code changes needed. Any name that has no file here keeps its current
fallback (monogram chip / live favicon), so a partial set is fine.

## Naming convention

Lowercase **kebab-case of the name exactly as it appears in the dashboard**:
spaces and symbols become `-`, dots in domains are kept.

| Where it shows | Expected filenames |
| --- | --- |
| Share-of-voice banks | `adcb.svg`, `emirates-nbd.svg`, `fab.svg`, `mashreq.svg`, `emirates-islamic.svg`, `dubai-islamic-bank.svg`, `adib.svg`, `rakbank.svg`, `hsbc-uae.svg`, `wio.svg`, `commercial-bank-of-dubai.svg`, `sharjah-islamic-bank.svg`, `liv.svg`, `standard-chartered.svg` |
| AI engines (backlog "asked on") | `chatgpt.svg`, `google-gemini.svg`, `google-ai-overviews.svg`, `google-ai-mode.svg`, `perplexity.svg` |
| Cited domains (citations + backlog) | the domain itself, e.g. `adcb.com.svg`, `emiratesnbd.com.svg`, `reddit.com.svg` — any domain without a file keeps its live favicon |
| App mark (sidebar, header, favicon) | `trendpulse.svg` |

## Artwork guidance

- Square canvas (any size — `viewBox` is what matters), rendered at 12–20 px,
  so **symbols/emblems work, full wordmark logos won't be readable**.
- Transparent background preferred; the app rounds the corners slightly.
- Keep files self-contained (no external `<image>` refs or fonts).
