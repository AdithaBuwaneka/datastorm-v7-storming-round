import Link from "next/link";
import { AlertTriangle, ShieldAlert, ShieldCheck, Activity } from "lucide-react";
import { api } from "@/lib/api";
import { fmtNumber, fmtLitres } from "@/lib/utils";
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
} from "@/components/ui/card";
import { KpiTile } from "@/components/kpi-tile";
import { RiskBadge } from "@/components/risk-badge";
import { Button } from "@/components/ui/button";
import { PaginationBar, buildPageHref } from "@/components/pagination-bar";
import { InsightFilterBar, SortableHeader, FilterConfig } from "../insight-filter-bar";
import { DormancyDonut } from "@/components/dashboard-charts";

const PAGE_SIZE = 20;

const RISK_RANKS: Record<string, number> = {
  "low": 1,
  "moderate": 2,
  "high": 3,
  "critical": 4,
};

export async function DormancyView({ searchParams }: { searchParams: Record<string, string | string[] | undefined> }) {
  const [bands, top, filters] = await Promise.all([
    api.dormancyBands(),
    api.dormancyTop(200),
    api.outletFilters(),
  ]);

  const rawPage = Array.isArray(searchParams.page) ? searchParams.page[0] : searchParams.page;
  const page = Math.max(1, Number(rawPage) || 1);
  const rawSearch = Array.isArray(searchParams.search) ? searchParams.search[0] : searchParams.search;
  const search = rawSearch || "";

  const qProv = Array.isArray(searchParams.province) ? searchParams.province[0] : searchParams.province;
  const qDist = Array.isArray(searchParams.distributor) ? searchParams.distributor[0] : searchParams.distributor;
  const qRisk = Array.isArray(searchParams.risk_band) ? searchParams.risk_band[0] : searchParams.risk_band;
  const qSort = Array.isArray(searchParams.sort_by) ? searchParams.sort_by[0] : searchParams.sort_by;
  const qDesc = Array.isArray(searchParams.descending) ? searchParams.descending[0] : searchParams.descending;
  const isDesc = qDesc === "true";

  const filterConfigs: FilterConfig[] = [
    {
      key: "province",
      label: "Province",
      options: filters.provinces.map(p => ({ label: p, value: p }))
    },
    {
      key: "distributor",
      label: "Distributor",
      options: filters.distributors.map(d => ({ label: d, value: d }))
    },
    {
      key: "risk_band",
      label: "Risk band",
      options: filters.risk_bands.map(r => ({ label: r, value: r }))
    }
  ];

  let filteredTop = top.filter((r: any) => {
    if (search && !r.Outlet_ID?.toLowerCase().includes(search.toLowerCase())) return false;
    if (qProv && r.Province !== qProv) return false;
    if (qDist && r.Distributor_ID !== qDist) return false;
    if (qRisk && r.risk_band !== qRisk) return false;
    return true;
  });

  if (qSort) {
    filteredTop.sort((a: any, b: any) => {
      if (qSort === "risk_band") {
        const aVal = RISK_RANKS[a.risk_band] || 0;
        const bVal = RISK_RANKS[b.risk_band] || 0;
        return isDesc ? bVal - aVal : aVal - bVal;
      }
      
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

  const totalPages = Math.max(1, Math.ceil(filteredTop.length / PAGE_SIZE));
  const safePage = Math.min(Math.max(1, page), totalPages);
  const start = (safePage - 1) * PAGE_SIZE;
  const slice = filteredTop.slice(start, start + PAGE_SIZE);

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
          label="Low risk"
          value={fmtNumber(bands.low)}
          icon={ShieldCheck}
          accent="success"
        />
        <KpiTile
          label="Moderate risk"
          value={fmtNumber(bands.moderate)}
          icon={Activity}
          accent="muted"
        />
        <KpiTile
          label="High risk"
          value={fmtNumber(bands.high)}
          icon={AlertTriangle}
          accent="warning"
        />
        <KpiTile
          label="Critical risk"
          value={fmtNumber(bands.critical)}
          icon={ShieldAlert}
          accent="danger"
        />
      </section>

      <Card className="mt-6">
        <CardHeader>
          <CardTitle>Risk band distribution</CardTitle>
          <CardDescription>
            Share of outlets in each predicted dormancy-risk band.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <DormancyDonut
            data={[
              { name: "Low", value: bands.low ?? 0 },
              { name: "Moderate", value: bands.moderate ?? 0 },
              { name: "High", value: bands.high ?? 0 },
              { name: "Critical", value: bands.critical ?? 0 },
            ].filter((d) => d.value > 0)}
          />
        </CardContent>
      </Card>

      <InsightFilterBar filters={filterConfigs} />

      <Card className="mt-6">
        <CardHeader>
          <CardTitle>Top-200 at-risk outlets</CardTitle>
          <CardDescription>
            Currently-active outlets ranked by dormancy risk. Send a sales rep
            before they lapse. Classifier 5-fold CV AUC ≈ 0.88.
          </CardDescription>
        </CardHeader>
        <CardContent className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-xs uppercase tracking-wider text-muted-foreground">
              <tr>
                <SortableHeader field="Outlet_ID" label="Outlet" className="px-2 py-2" />
                <SortableHeader field="Province" label="Province" className="px-2 py-2" />
                <SortableHeader field="Distributor_ID" label="Distributor" className="px-2 py-2" />
                <SortableHeader field="active_months" label="Active months" className="px-2 py-2 text-right" />
                <SortableHeader field="monthly_volume_mean" label="Recent avg" className="px-2 py-2 text-right" />
                <SortableHeader field="Cooler_Count" label="Coolers" className="px-2 py-2 text-center" />
                <SortableHeader field="risk_band" label="Risk band" className="px-2 py-2 text-center" />
                <SortableHeader field="dormancy_risk_score" label="Risk score" className="px-2 py-2 text-right" />
                <th className="px-2 py-2" />
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {slice.map((r: any) => (
                <tr key={r.Outlet_ID} className="hover:bg-muted/30">
                  <td className="px-2 py-2 font-mono text-xs">{r.Outlet_ID}</td>
                  <td className="px-2 py-2">{r.Province}</td>
                  <td className="px-2 py-2 font-mono text-xs">
                    {r.Distributor_ID}
                  </td>
                  <td className="px-2 py-2 text-right">{r.active_months}</td>
                  <td className="px-2 py-2 text-right">
                    {fmtLitres(r.monthly_volume_mean, 1)}
                  </td>
                  <td className="px-2 py-2 text-center">{r.Cooler_Count}</td>
                  <td className="px-2 py-2 text-center">
                    <RiskBadge band={r.risk_band} />
                  </td>
                  <td className="px-2 py-2 text-right font-mono text-xs">
                    {(r.dormancy_risk_score ?? 0).toFixed(3)}
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
                  <td colSpan={9} className="px-2 py-8 text-center text-muted-foreground">
                    No results found.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
          <PaginationBar
            page={safePage}
            totalPages={totalPages}
            totalRows={filteredTop.length}
            label="at-risk outlets"
            pageHref={(p) => buildPageHref("/insights", "dormancy", p, extraParams)}
          />
        </CardContent>
      </Card>
    </>
  );
}
