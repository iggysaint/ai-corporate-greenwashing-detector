# ESG Integrity Intelligence — Frontend

Web interface for the AI Corporate Greenwashing Detector. It calls the existing FastAPI backend directly from the
browser and shows its results without changing them: scores, pillar results, claim evaluations and evidence quotes all
come from the API.

**Workflow:** select a market → find a company → run an ESG Integrity Assessment → view the score → investigate claims → inspect evidence → read the methodology.

## Stack

- Next.js 16 (App Router, Cache Components, Turbopack), React 19, TypeScript (strict)
- Tailwind CSS v4 with design tokens in `src/app/globals.css`
- Lucide icons and Radix Dialog (accessible side panels and the mobile navigation drawer)
- Vitest for unit tests

## Screens

| Route | Screen | Backend endpoints |
| --- | --- | --- |
| `/` | Overview: introduction, ticker search, workflow, score scope, GSE directory | `GET /api/v1/gse/companies` |
| `/explorer` | Company Explorer: exact-ticker lookup for SEC, browsable directory for GSE | `GET /api/v1/gse/companies` |
| `/company` | Company Profile: SEC metadata and filings, or GSE details, documents and a report-URL form | `GET /companies/{t}`, `/filings`, `/filings/latest`, `/filings/latest/document` (on demand); `GET /gse/companies/{t}`; score history |
| `/assessment` | ESG Integrity Score dashboard | `GET /companies/{t}/score/breakdown`; `GET /gse/companies/{t}/score/breakdown?source_url=&reporting_period=` |
| `/claims` | Claims & Evidence explorer with claim detail panel | Uses the stored breakdown; SEC claims can also load `GET /companies/{t}/claims/{id}/evaluation` |
| `/history` | Assessment History | `GET /companies/{t}/score/history`, `GET /gse/companies/{t}/score/history` |
| `/methodology` | Methodology & Transparency | Static content from `docs/ESG_INTEGRITY_SCORE_METHODOLOGY.md` |

Every route is under `/api/v1` except `/health`, which drives the "API connected" indicator.

The selected market and company are carried in the URL (`?market=us_sec&ticker=AAPL`), so every screen can be linked
and survives a reload. Assessment results are kept in `sessionStorage` for the current tab only, matching the backend's
in-memory history.

## Running locally

Run these from the repository root.

1. **Backend:**

   ```bash
   uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
   ```

   The backend's `CORS_ALLOW_ORIGINS` already includes `http://localhost:3000` and `http://127.0.0.1:3000`. To serve
   the frontend from another origin, add it in the backend `.env`, for example
   `CORS_ALLOW_ORIGINS=["https://esg.example.com"]`.

2. **Frontend** (Node.js 20.9 or later):

   ```bash
   cd frontend
   npm install
   cp .env.example .env.local   # adjust NEXT_PUBLIC_API_BASE_URL if needed
   npm run dev
   ```

   Then open http://localhost:3000.

### Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `NEXT_PUBLIC_API_BASE_URL` | `http://127.0.0.1:8000` | FastAPI base URL that the browser calls |
| `NEXT_PUBLIC_ANALYSIS_TIMEOUT_MS` | `300000` | Timeout for full assessments; values below 60000 are ignored |

Both are `NEXT_PUBLIC_` values: they are compiled into browser code at build time and must never hold secrets. The
frontend needs no API keys; the SEC user agent and LLM key stay on the backend.

## Quality checks

```bash
npm run typecheck   # next typegen + tsc --noEmit
npm run lint        # ESLint (next/core-web-vitals + TypeScript)
npm test            # Vitest unit tests (API client, error mapping, validation, null handling)
npm run build       # production build
```

### Verifying the live connection

1. Start the backend and run `curl http://127.0.0.1:8000/health`. It should return `"status": "healthy"`.
2. Start the frontend. The top bar should show **API connected**. If it shows **API unreachable**, check
   `NEXT_PUBLIC_API_BASE_URL` and the backend's `CORS_ALLOW_ORIGINS`.
3. SEC: open the Explorer, enter `AAPL`, and run the assessment from the profile. The first run downloads and
   processes the 10-K and can take several minutes.
4. GSE: open `MTNGH`, which has verified reports on file, and choose **Assess** on a report. For an issuer with no
   report on file, the profile asks for a public report URL, and running without one returns a clear "Report URL
   required" (HTTP 422) state.

## Design notes

- **Missing data is never zero.** Null overall and pillar scores render as "Insufficient Data" with a dashed or hatched
  treatment. Insufficient-evidence claims are hatched and marked "Excluded".
- **No invented classifications.** There are no risk ratings or fabricated aggregate statistics. Positive factors and
  concerns are shown exactly as the backend returns them.
- **Per-claim confidence.** The score breakdown does not include per-claim confidence. The claims table shows the
  confidence adjustment the scoring engine recorded (+3 high, −3 low, none for medium). For SEC claims, the panel can
  load the full evaluation record: confidence, caveat text and evaluation mode.
- **Long assessments** run in the root workspace provider, so they continue while the user browses (Next.js keeps
  inactive pages mounted but hidden and cleans up their effects). The UI shows elapsed time and the pipeline steps; it
  does not show a fake percentage.
- **Safety.** External data is rendered as text only (no `dangerouslySetInnerHTML`). External links are limited to
  http(s) and open with `noopener noreferrer`. Path segments are URL-encoded. Report URLs get a client-side sanity
  check, but the backend's SSRF protection remains the security boundary.
