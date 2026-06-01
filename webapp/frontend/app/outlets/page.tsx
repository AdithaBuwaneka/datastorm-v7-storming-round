import Link from "next/link";
import { api } from "@/lib/api";
import { fmtLitres, fmtNumber } from "@/lib/utils";
import { PageHeader } from "@/components/page-header";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { RiskBadge } from "@/components/risk-badge";
import { FilterBar } from "./filter-bar";

type Search = Record<string, string | string[] | undefined>;

function first(v: string | string[] | undefined): string | undefined {
  return Array.isArray(v) ? v[0] : v;
}

const PAGE_SIZE = 50;

export default async function OutletsPage({
  searchParams,
}: {
  searchParams: Search;
}) {
  const page = Math.max(1, Number(first(searchParams.page) || 1));
  const params = {
    page,
    page_size: PAGE_SIZE,
    province: first(searchParams.province),
    distributor: first(searchParams.distributor),
    outlet_type: first(searchParams.outlet_type),
    outlet_size: first(searchParams.outlet_size),
    risk_band: first(searchParams.risk_band),
    search: first(searchParams.search),
    sort_by: first(searchParams.sort_by) ?? "Maximum_Monthly_Liters",
    descending: first(searchParams.descending) !== "false",
  };

  let rows: any[] = [];
  let total = 0;
  let n_pages = 1;
  let filters = {
    provinces: [],
    distributors: [],
    outlet_types: [],
    outlet_sizes: [],
    risk_bands: ["low", "moderate", "high", "critical"],
  };
  let error: string | null = null;
  try {
    const [resp, filt] = await Promise.all([
      api.listOutlets(params),
      api.outletFilters(),
    ]);
    rows = resp.rows;
    total = resp.total;
    n_pages = resp.n_pages;
    filters = { ...filters, ...filt };
  } catch (e) {
    error = e instanceof Error ? e.message : String(e);
  }

  return (
    <>
      <PageHeader
        title="Outlets"
        description={
          error
            ? "Backend not reachable"
            : `${fmtNumber(total)} outlets matching the current filters`
        }
      />

      <FilterBar filters={filters} />

      {error ? (
        <Card className="mt-6">
          <pre className="rounded-md bg-muted p-3 text-xs">{error}</pre>
        </Card>
      ) : (
        <>
          <div className="mt-6 overflow-x-auto rounded-lg border border-border bg-card">
            <table className="w-full text-sm">
              <thead className="bg-muted/50 text-left text-xs uppercase tracking-wider text-muted-foreground">
                <tr>
                  <th className="px-4 py-3">Outlet</th>
                  <th className="px-4 py-3">Type</th>
                  <th className="px-4 py-3">Size</th>
                  <th className="px-4 py-3">Province</th>
                  <th className="px-4 py-3">Distributor</th>
                  <th className="px-4 py-3 text-right">Predicted Jan 2026</th>
                  <th className="px-4 py-3 text-right">Recent avg</th>
                  <th className="px-4 py-3 text-right">Coolers</th>
                  <th className="px-4 py-3 text-center">Risk</th>
                  <th className="px-4 py-3" />
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {rows.map((r) => (
                  <tr key={r.Outlet_ID} className="hover:bg-muted/30">
                    <td className="px-4 py-3 font-mono text-xs">{r.Outlet_ID}</td>
                    <td className="px-4 py-3">{r.Outlet_Type}</td>
                    <td className="px-4 py-3">
                      <Badge variant="outline">{r.Outlet_Size}</Badge>
                    </td>
                    <td className="px-4 py-3">{r.Province}</td>
                    <td className="px-4 py-3 font-mono text-xs">{r.Distributor_ID}</td>
                    <td className="px-4 py-3 text-right font-medium">
                      {fmtLitres(r.Maximum_Monthly_Liters, 1)}
                    </td>
                    <td className="px-4 py-3 text-right text-muted-foreground">
                      {fmtLitres(r.monthly_volume_mean, 1)}
                    </td>
                    <td className="px-4 py-3 text-right">{r.Cooler_Count}</td>
                    <td className="px-4 py-3 text-center">
                      <RiskBadge band={r.risk_band} />
                    </td>
                    <td className="px-4 py-3 text-right">
                      <Link href={`/outlets/${r.Outlet_ID}`}>
                        <Button size="sm" variant="outline">
                          Open →
                        </Button>
                      </Link>
                    </td>
                  </tr>
                ))}
                {rows.length === 0 && (
                  <tr>
                    <td
                      colSpan={10}
                      className="px-4 py-12 text-center text-muted-foreground"
                    >
                      No outlets match the current filters.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          <Pagination
            page={page}
            n_pages={n_pages}
            total={total}
            searchParams={searchParams}
          />
        </>
      )}
    </>
  );
}

function Pagination({
  page,
  n_pages,
  total,
  searchParams,
}: {
  page: number;
  n_pages: number;
  total: number;
  searchParams: Search;
}) {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(searchParams)) {
    if (k === "page") continue;
    const value = Array.isArray(v) ? v[0] : v;
    if (value != null) sp.set(k, value);
  }
  const link = (p: number) => {
    const next = new URLSearchParams(sp);
    next.set("page", String(p));
    return `/outlets?${next.toString()}`;
  };

  return (
    <div className="mt-4 flex items-center justify-between text-sm text-muted-foreground">
      <span>
        Page {page} of {n_pages} · {fmtNumber(total)} outlets
      </span>
      <div className="flex gap-2">
        <Link href={link(Math.max(1, page - 1))}>
          <Button variant="outline" size="sm" disabled={page <= 1}>
            ← Prev
          </Button>
        </Link>
        <Link href={link(Math.min(n_pages, page + 1))}>
          <Button variant="outline" size="sm" disabled={page >= n_pages}>
            Next →
          </Button>
        </Link>
      </div>
    </div>
  );
}
