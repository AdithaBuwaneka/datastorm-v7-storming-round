import Link from "next/link";
import { Snowflake, TrendingUp, Wallet, Clock } from "lucide-react";
import { api } from "@/lib/api";
import { fmtLKR, fmtLitres, fmtNumber } from "@/lib/utils";
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
} from "@/components/ui/card";
import { KpiTile } from "@/components/kpi-tile";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { PaginationBar, buildPageHref } from "@/components/pagination-bar";
import { InsightFilterBar, SortableHeader, FilterConfig } from "../insight-filter-bar";
import { CoolerNpvBar } from "@/components/dashboard-charts";

const PAGE_SIZE = 20;

export async function CoolerRoiView({ searchParams }: { searchParams: Record<string, string | string[] | undefined> }) {
  const [summary, top100, filters] = await Promise.all([
    api.coolerRoiSummary(),
    api.coolerRoiTop100(),
    api.outletFilters(),
  ]);

  const rawPage = Array.isArray(searchParams.page) ? searchParams.page[0] : searchParams.page;
  const page = Math.max(1, Number(rawPage) || 1);
  const rawSearch = Array.isArray(searchParams.search) ? searchParams.search[0] : searchParams.search;
  const search = rawSearch || "";

  const qType = Array.isArray(searchParams.outlet_type) ? searchParams.outlet_type[0] : searchParams.outlet_type;
  const qDist = Array.isArray(searchParams.distributor) ? searchParams.distributor[0] : searchParams.distributor;
  const qGreen = Array.isArray(searchParams.greenfield) ? searchParams.greenfield[0] : searchParams.greenfield;
  const qSort = Array.isArray(searchParams.sort_by) ? searchParams.sort_by[0] : searchParams.sort_by;
  const qDesc = Array.isArray(searchParams.descending) ? searchParams.descending[0] : searchParams.descending;
  const isDesc = qDesc === "true";

  const filterConfigs: FilterConfig[] = [
    {
      key: "outlet_type",
      label: "Type",
      options: filters.outlet_types.map(t => ({ label: t, value: t }))
    },
    {
      key: "distributor",
      label: "Distributor",
      options: filters.distributors.map(d => ({ label: d, value: d }))
    },
    {
      key: "greenfield",
      label: "Greenfield",
      options: [{ label: "Yes", value: "true" }, { label: "No", value: "false" }]
    }
  ];

  let filteredTop100 = top100.filter((r: any) => {
    if (search && !r.Outlet_ID?.toLowerCase().includes(search.toLowerCase())) return false;
    if (qType && r.Outlet_Type !== qType) return false;
    if (qDist && r.Distributor_ID !== qDist) return false;
    if (qGreen) {
      if (qGreen === "true" && !r.is_greenfield) return false;
      if (qGreen === "false" && r.is_greenfield) return false;
    }
    return true;
  });

  if (qSort) {
    filteredTop100.sort((a: any, b: any) => {
      let aVal = a[qSort];
      let bVal = b[qSort];
      if (typeof aVal === 'string' && typeof bVal === 'string') {
        return isDesc ? bVal.localeCompare(aVal) : aVal.localeCompare(bVal);
      }
      aVal = Number(aVal) || 0;
      bVal = Number(bVal) || 0;
      return isDesc ? bVal - aVal : aVal - bVal;
    });
  }

  const totalPages = Math.max(1, Math.ceil(filteredTop100.length / PAGE_SIZE));
  const safePage = Math.min(Math.max(1, page), totalPages);
  const start = (safePage - 1) * PAGE_SIZE;
  const slice = filteredTop100.slice(start, start + PAGE_SIZE);

  const netValue = (summary.top100_24mo_margin_LKR ?? 0) - (summary.top100_total_capex_LKR ?? 0);

  // Convert searchParams to Record<string, string> for pagination
  const extraParams: Record<string, string> = {};
  for (const [k, v] of Object.entries(searchParams)) {
    if (k !== 'page' && k !== 'view') {
      extraParams[k] = Array.isArray(v) ? (v[0] || "") : (v || "");
    }
  }

  return (
    <>
      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <KpiTile
          label="Outlets without a cooler"
          value={fmtNumber(summary.outlets_without_cooler)}
          icon={Snowflake}
        />
        <KpiTile
          label="Material business cases"
          value={fmtNumber(summary.material_cases)}
          sublabel="monthly uplift ≥ 5 L"
          icon={TrendingUp}
          accent="success"
        />
        <KpiTile
          label="Top-100 capex"
          value={fmtLKR(summary.top100_total_capex_LKR)}
          sublabel="LKR 50,000 per cooler"
          icon={Wallet}
          accent="warning"
        />
        <KpiTile
          label="Top-100 24-month margin"
          value={fmtLKR(summary.top100_24mo_margin_LKR)}
          sublabel={`Net value: ${fmtLKR(netValue)}`}
          icon={Clock}
          accent="success"
        />
      </section>

      <Card className="mt-6">
        <CardHeader>
          <CardTitle>Top 10 outlets by 24-month NPV</CardTitle>
          <CardDescription>
            The highest-return cooler deployments — net present value over a
            24-month horizon.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <CoolerNpvBar
            data={[...top100]
              .sort(
                (a: any, b: any) =>
                  (b.npv_24mo_LKR ?? 0) - (a.npv_24mo_LKR ?? 0),
              )
              .slice(0, 10)
              .map((r: any) => ({
                name: r.Outlet_ID,
                value: r.npv_24mo_LKR ?? 0,
              }))}
          />
        </CardContent>
      </Card>

      <InsightFilterBar filters={filterConfigs} />

      <Card className="mt-6">
        <CardHeader>
          <CardTitle>Top-100 cooler deployment list</CardTitle>
          <CardDescription>
            Ranked by 24-month NPV. Median payback{" "}
            <span className="font-semibold text-foreground">
              {(summary.top100_median_payback_months ?? 0).toFixed(1)} months
            </span>{" "}
            at LKR 50,000 unit cost, 12% gross margin, 12% cost of capital.
          </CardDescription>
        </CardHeader>
        <CardContent className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-xs uppercase tracking-wider text-muted-foreground">
              <tr>
                <SortableHeader field="Outlet_ID" label="Outlet" className="px-2 py-2" />
                <SortableHeader field="Outlet_Type" label="Type" className="px-2 py-2" />
                <SortableHeader field="Distributor_ID" label="Distributor" className="px-2 py-2" />
                <SortableHeader field="monthly_uplift_L" label="Monthly uplift" className="px-2 py-2 text-right" />
                <SortableHeader field="payback_months" label="Payback" className="px-2 py-2 text-right" />
                <SortableHeader field="npv_24mo_LKR" label="24-mo NPV" className="px-2 py-2 text-right" />
                <SortableHeader field="is_greenfield" label="Greenfield" className="px-2 py-2 text-center" />
                <th className="px-2 py-2" />
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {slice.map((r: any) => (
                <tr key={r.Outlet_ID} className="hover:bg-muted/30">
                  <td className="px-2 py-2 font-mono text-xs">{r.Outlet_ID}</td>
                  <td className="px-2 py-2">{r.Outlet_Type}</td>
                  <td className="px-2 py-2 font-mono text-xs">
                    {r.Distributor_ID}
                  </td>
                  <td className="px-2 py-2 text-right">
                    {fmtLitres(r.monthly_uplift_L, 1)}
                  </td>
                  <td className="px-2 py-2 text-right">
                    {(r.payback_months ?? 0).toFixed(1)} mo
                  </td>
                  <td className="px-2 py-2 text-right font-semibold">
                    {fmtLKR(r.npv_24mo_LKR)}
                  </td>
                  <td className="px-2 py-2 text-center">
                    {r.is_greenfield ? (
                      <Badge variant="success">Yes</Badge>
                    ) : (
                      <Badge variant="muted">No</Badge>
                    )}
                  </td>
                  <td className="px-2 py-2 text-right">
                    <Link href={`/outlets/${r.Outlet_ID}`}>
                      <Button size="sm" variant="outline">
                        View
                      </Button>
                    </Link>
                  </td>
                </tr>
              ))}
              {slice.length === 0 && (
                <tr>
                  <td colSpan={8} className="px-2 py-8 text-center text-muted-foreground">
                    No results found.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
          <PaginationBar
            page={safePage}
            totalPages={totalPages}
            totalRows={filteredTop100.length}
            label="outlets"
            pageHref={(p) => buildPageHref("/insights", "cooler-roi", p, extraParams)}
          />
        </CardContent>
      </Card>
    </>
  );
}
