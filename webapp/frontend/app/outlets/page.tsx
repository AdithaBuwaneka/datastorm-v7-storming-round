import Link from "next/link";
import { api } from "@/lib/api";
import { fmtLitres, fmtNumber } from "@/lib/utils";
import { PageHeader } from "@/components/page-header";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { RiskBadge } from "@/components/risk-badge";
import { FilterBar } from "./filter-bar";

type Search = Record<string, string | string[] | undefined>;

function first(v: string | string[] | undefined): string | undefined {
  return Array.isArray(v) ? v[0] : v;
}

const PAGE_SIZE = 20;

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
  let filters: {
    provinces: string[];
    distributors: string[];
    outlet_types: string[];
    outlet_sizes: string[];
    risk_bands: string[];
  } = {
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
          <div
            className="mt-6 overflow-hidden rounded-lg border border-border bg-card"
            style={{ minHeight: `${PAGE_SIZE * 44 + 56}px` }}
          >
            <table className="w-full table-fixed text-sm">
              <thead className="bg-muted/50 text-left text-xs uppercase tracking-wider text-muted-foreground">
                <tr>
                  <th className="w-[12%] whitespace-nowrap px-3 py-2.5">Outlet</th>
                  <th className="w-[22%] whitespace-nowrap px-3 py-2.5">
                    Type / Size
                  </th>
                  <th className="hidden w-[12%] whitespace-nowrap px-3 py-2.5 md:table-cell">
                    Province
                  </th>
                  <th className="hidden w-[13%] whitespace-nowrap px-3 py-2.5 lg:table-cell">
                    Distributor
                  </th>
                  <th className="w-[16%] whitespace-nowrap px-3 py-2.5 text-right">
                    Predicted Jan 2026
                  </th>
                  <th className="hidden w-[11%] whitespace-nowrap px-3 py-2.5 text-right xl:table-cell">
                    Recent avg
                  </th>
                  <th className="hidden w-[7%] whitespace-nowrap px-3 py-2.5 text-right sm:table-cell">
                    Coolers
                  </th>
                  <th className="w-[8%] whitespace-nowrap px-3 py-2.5 text-center">
                    Risk
                  </th>
                  <th className="w-[8%] px-3 py-2.5" />
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {rows.map((r) => (
                  <tr key={r.Outlet_ID} className="hover:bg-muted/30">
                    <td className="whitespace-nowrap px-3 py-2.5 font-mono text-xs">
                      {r.Outlet_ID}
                    </td>
                    <td className="whitespace-nowrap px-3 py-2.5">
                      <span className="font-medium">{r.Outlet_Type}</span>
                      <span className="ml-2 text-xs text-muted-foreground">
                        {r.Outlet_Size}
                      </span>
                    </td>
                    <td className="hidden whitespace-nowrap px-3 py-2.5 md:table-cell">
                      {r.Province}
                    </td>
                    <td className="hidden whitespace-nowrap px-3 py-2.5 font-mono text-xs lg:table-cell">
                      {r.Distributor_ID}
                    </td>
                    <td className="whitespace-nowrap px-3 py-2.5 text-right font-medium">
                      {fmtLitres(r.Maximum_Monthly_Liters, 1)}
                    </td>
                    <td className="hidden whitespace-nowrap px-3 py-2.5 text-right text-muted-foreground xl:table-cell">
                      {fmtLitres(r.monthly_volume_mean, 1)}
                    </td>
                    <td className="hidden px-3 py-2.5 text-right sm:table-cell">
                      {r.Cooler_Count}
                    </td>
                    <td className="px-3 py-2.5 text-center">
                      <RiskBadge band={r.risk_band} />
                    </td>
                    <td className="whitespace-nowrap px-3 py-2.5 text-right">
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
                      colSpan={9}
                      className="px-3 py-12 text-center text-muted-foreground"
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

function buildPageList(current: number, total: number): (number | "...")[] {
  if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1);
  const pages: (number | "...")[] = [1];
  const start = Math.max(2, current - 1);
  const end = Math.min(total - 1, current + 1);
  if (start > 2) pages.push("...");
  for (let p = start; p <= end; p++) pages.push(p);
  if (end < total - 1) pages.push("...");
  pages.push(total);
  return pages;
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

  const pages = buildPageList(page, n_pages);

  return (
    <div className="mt-4 flex flex-wrap items-center justify-between gap-3 text-sm text-muted-foreground">
      <span>
        Page <span className="font-semibold text-foreground">{page}</span> of{" "}
        {fmtNumber(n_pages)} · {fmtNumber(total)} outlets
      </span>
      <nav className="flex items-center gap-1">
        <Link href={link(Math.max(1, page - 1))} aria-disabled={page <= 1}>
          <Button
            variant="outline"
            size="sm"
            disabled={page <= 1}
            className="h-8"
          >
            ← Prev
          </Button>
        </Link>

        {pages.map((p, i) =>
          p === "..." ? (
            <span
              key={`ell-${i}`}
              className="px-2 text-xs text-muted-foreground"
            >
              …
            </span>
          ) : (
            <Link key={p} href={link(p)}>
              <Button
                variant={p === page ? "default" : "outline"}
                size="sm"
                className="h-8 min-w-8 px-2.5 font-mono text-xs"
              >
                {p}
              </Button>
            </Link>
          ),
        )}

        <Link
          href={link(Math.min(n_pages, page + 1))}
          aria-disabled={page >= n_pages}
        >
          <Button
            variant="outline"
            size="sm"
            disabled={page >= n_pages}
            className="h-8"
          >
            Next →
          </Button>
        </Link>
      </nav>
    </div>
  );
}
