---
title: DataX Outlet Intelligence API
emoji: 📊
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
license: apache-2.0
short_description: FastAPI backend serving outlet potential, SHAP attribution, and Gemini-grounded XAI narratives for 20,000 Sri Lankan beverage outlets.
---

# DataX Outlet Intelligence — Backend (Hugging Face Space)

FastAPI service that exposes the gold-layer artifacts of the
DataStorm v7.0 pipeline through 18 JSON endpoints, including an
on-demand Gemini 2.5 Flash narrative for any outlet.

This Space is **automatically rebuilt** on every push to the `main`
branch of the source GitHub repo via a GitHub Actions workflow.

| | |
|---|---|
| Source | <https://github.com/AdithaBuwaneka/DataX-DataStorm-7.0> |
| Workflow | `.github/workflows/deploy-backend-to-hf.yml` |
| Health probe | `GET /health` |
| OpenAPI / Swagger | `GET /docs` |

## Required Space secret

| Name | Where to set | Purpose |
|---|---|---|
| `GEMINI_API_KEY` | Settings → Variables and secrets → New secret | Enables the `/api/xai/explain/{id}` Gemini narrative endpoint |

Without `GEMINI_API_KEY` the rest of the API still works; only the
narrative endpoint returns HTTP 503.

## Endpoints (summary)

| Endpoint | Returns |
|---|---|
| `GET /health` | Liveness probe + data-loaded confirmation |
| `GET /api/summary` | Dashboard KPI tiles |
| `GET /api/outlets` | Paginated outlet list |
| `GET /api/outlets/{id}` | Drill-down + SHAP + counterfactual + actions + cooler ROI |
| `POST /api/xai/explain/{id}` | Gemini narrative |
| `GET /api/budget/*` | LKR 5M Western Province allocation |
| `GET /api/cooler-roi/*` | Top-100 cooler deployment |
| `GET /api/dormancy/*` | At-risk outlets |
| `GET /api/scorecard` | 10-distributor benchmark |
| `GET /api/territories` | HDBSCAN clusters |
| `GET /api/forensics` | Beyond-DQ forensic findings |
| `GET /api/shap/global` | Global mean \|SHAP\| ranking |

Full reference at <https://huggingface.co/spaces/adithaf7/datax-outlet-intelligence-api/docs>.
