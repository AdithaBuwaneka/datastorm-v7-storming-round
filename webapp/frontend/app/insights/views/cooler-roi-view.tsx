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

export async function CoolerRoiView() {
  const [summary, top100] = await Promise.all([
    api.coolerRoiSummary(),
    api.coolerRoiTop100(),
  ]);

  const netValue =
    (summary.top100_24mo_margin_LKR ?? 0) -
    (summary.top100_total_capex_LKR ?? 0);

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
                <th className="px-2 py-2">Outlet</th>
                <th className="px-2 py-2">Type</th>
                <th className="px-2 py-2">Distributor</th>
                <th className="px-2 py-2 text-right">Monthly uplift</th>
                <th className="px-2 py-2 text-right">Payback</th>
                <th className="px-2 py-2 text-right">24-mo NPV</th>
                <th className="px-2 py-2 text-center">Greenfield</th>
                <th className="px-2 py-2" />
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {top100.map((r: any) => (
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
            </tbody>
          </table>
        </CardContent>
      </Card>
    </>
  );
}
