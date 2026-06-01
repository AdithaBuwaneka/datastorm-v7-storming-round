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

export async function DormancyView() {
  const [bands, top] = await Promise.all([
    api.dormancyBands(),
    api.dormancyTop(200),
  ]);

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
                <th className="px-2 py-2">Outlet</th>
                <th className="px-2 py-2">Province</th>
                <th className="px-2 py-2">Distributor</th>
                <th className="px-2 py-2 text-right">Active months</th>
                <th className="px-2 py-2 text-right">Recent avg</th>
                <th className="px-2 py-2 text-center">Coolers</th>
                <th className="px-2 py-2 text-center">Risk band</th>
                <th className="px-2 py-2 text-right">Risk score</th>
                <th className="px-2 py-2" />
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {top.map((r: any) => (
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
            </tbody>
          </table>
        </CardContent>
      </Card>
    </>
  );
}
