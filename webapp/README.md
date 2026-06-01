# Outlet Intelligence Web App

A two-process decision-support tool that turns the pipeline outputs into an
interactive workspace for sales managers, distributors, and trade-marketing
teams.

```
webapp/
├── backend/    FastAPI (Python) — 18 JSON endpoints + Gemini XAI
└── frontend/   Next.js 14 (TypeScript + Tailwind) — Dashboard, Outlets, Insights
```

## What the app exposes

| Route | What you see |
|---|---|
| `/` | Dashboard with KPI tiles (predictions, budget, risk exposure, cooler value) |
| `/outlets` | Paginated and filterable table of all 20,000 outlets |
| `/outlets/[id]` | Drill-down: predicted potential, SHAP drivers, what-if deltas, recommended actions, cooler ROI, AI-generated narrative |
| `/insights?view=budget` | LKR 5M Western Province allocation split by distributor and channel |
| `/insights?view=cooler-roi` | Top-100 cooler deployment list with payback and 24-month NPV |
| `/insights?view=dormancy` | Top-200 at-risk outlets ranked by dormancy classifier |
| `/insights?view=scorecard` | 10-distributor operational benchmark |
| `/insights?view=territories` | HDBSCAN sub-province territories on an interactive map |
| `/insights?view=forensics` | Forensic findings produced during cleaning |

## Local setup

### Prerequisites

- Python 3.10+
- Node.js 20+ and npm
- A Google Gemini API key (free tier works) — get one at
  <https://aistudio.google.com/app/apikey>

You must run the pipeline at least once before starting the app so the
parquets and audit CSVs exist:

```bash
# From the repository root
pip install -r requirements.txt
python -m src.run_pipeline
```

### 1. Backend (FastAPI on :8000)

```bash
cd webapp/backend
pip install -r requirements.txt
cp .env.example .env            # Windows PowerShell: copy .env.example .env
# Edit .env and set GEMINI_API_KEY=<your_key>
python -m uvicorn main:app --port 8000
```

Confirm by opening <http://127.0.0.1:8000/health> — you should see
`{"status":"ok", "gemini_configured": true, ...}`.

### 2. Frontend (Next.js on :3000)

In a second terminal:

```bash
cd webapp/frontend
npm install
npm run dev
```

Open <http://localhost:3000>. The frontend talks to the backend at
`http://127.0.0.1:8000` by default. Override with the
`NEXT_PUBLIC_API_BASE` env var if your backend runs elsewhere.

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `GEMINI_API_KEY` | — (required) | Google Gemini key (backend `.env`) |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Which Gemini model to call |
| `REPO_ROOT` | auto-detected | Override repo root for the backend cache |
| `NEXT_PUBLIC_API_BASE` | `http://127.0.0.1:8000` | Frontend → backend URL |

`webapp/backend/.env` is gitignored. Never commit your real key.

## Production build (optional)

```bash
cd webapp/frontend
npm run build
npm start    # serves the production bundle on :3000
```

The backend can be served behind any standard ASGI host (uvicorn / hypercorn).
For demo / pitch use the dev commands above.
