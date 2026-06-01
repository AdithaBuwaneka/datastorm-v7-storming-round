/**
 * Typed API client for the FastAPI backend.
 * NEXT_PUBLIC_API_BASE is set by next.config.js (default http://127.0.0.1:8000).
 */
const BASE =
  process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000";

async function jsonFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    cache: "no-store",
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      if (body?.detail) detail = body.detail;
    } catch {
      /* ignore */
    }
    throw new Error(`${res.status} ${detail}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => jsonFetch<{ status: string; outlets_loaded: number; gemini_configured: boolean }>("/health"),
  summary: () => jsonFetch<Record<string, unknown>>("/api/summary"),

  listOutlets: (params: Record<string, string | number | boolean | undefined> = {}) => {
    const usp = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== "" && v !== null) usp.set(k, String(v));
    }
    const q = usp.toString();
    return jsonFetch<{
      total: number;
      page: number;
      page_size: number;
      n_pages: number;
      rows: Record<string, any>[];
    }>(`/api/outlets/${q ? `?${q}` : ""}`);
  },

  outletFilters: () => jsonFetch<{
    provinces: string[];
    distributors: string[];
    outlet_types: string[];
    outlet_sizes: string[];
    risk_bands: string[];
  }>("/api/outlets/filters"),

  outletDetail: (id: string) => jsonFetch<{
    outlet: Record<string, any>;
    top_drivers: { direction: "positive" | "negative"; feature: string; shap: number }[];
    counterfactual: Record<string, number>;
    recommended_actions: Record<string, any>[];
    cooler_roi: Record<string, any>;
  }>(`/api/outlets/${encodeURIComponent(id)}`),

  explain: (id: string) => jsonFetch<{
    outlet_id: string;
    payload: Record<string, any>;
    narrative: string;
  }>(`/api/xai/explain/${encodeURIComponent(id)}`, { method: "POST" }),

  budgetByDistributor: () => jsonFetch<Record<string, any>[]>("/api/budget/distributors"),
  budgetByChannel: () => jsonFetch<{ totals: Record<string, number>; rows: Record<string, any>[] }>("/api/budget/channels"),
  budgetOutlets: (limit = 200) => jsonFetch<Record<string, any>[]>(`/api/budget/outlets?limit=${limit}`),

  coolerRoiTop100: () => jsonFetch<Record<string, any>[]>("/api/cooler-roi/top100"),
  coolerRoiSummary: () => jsonFetch<Record<string, number>>("/api/cooler-roi/summary"),

  dormancyTop: (limit = 200) => jsonFetch<Record<string, any>[]>(`/api/dormancy/top?limit=${limit}`),
  dormancyBands: () => jsonFetch<Record<string, number>>("/api/dormancy/bands"),

  scorecard: () => jsonFetch<Record<string, any>[]>("/api/scorecard"),
  territories: () => jsonFetch<Record<string, any>[]>("/api/territories"),
  forensics: () => jsonFetch<Record<string, any>[]>("/api/forensics"),
  shapGlobal: (limit = 30) => jsonFetch<Record<string, any>[]>(`/api/shap/global?limit=${limit}`),
};
