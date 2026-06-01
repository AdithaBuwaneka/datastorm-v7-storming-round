import { api } from "@/lib/api";
import { fmtNumber, fmtLitres } from "@/lib/utils";
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
} from "@/components/ui/card";

function HealthBar({ z }: { z: number }) {
  // Map z-score (typically -2..+2) onto a 0..100 fill width
  const pct = Math.max(0, Math.min(100, ((z + 2) / 4) * 100));
  const tone =
    z >= 0.5 ? "bg-success" : z >= -0.5 ? "bg-primary" : "bg-danger";
  return (
    <div className="relative h-2 w-32 rounded-full bg-muted">
      <div
        className={`absolute inset-y-0 left-0 rounded-full ${tone}`}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

export async function ScorecardView() {
  const rows = await api.scorecard();
  return (
    <Card>
      <CardHeader>
        <CardTitle>Distributor scorecard</CardTitle>
        <CardDescription>
          Ten distributors ranked by composite z-scaled operational health
          across coverage, penetration, volume, cooler density, spatial
          demand, predicted potential, YoY growth and risk exposure.
        </CardDescription>
      </CardHeader>
      <CardContent className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-left text-xs uppercase tracking-wider text-muted-foreground">
            <tr>
              <th className="px-2 py-2">Rank</th>
              <th className="px-2 py-2">Distributor</th>
              <th className="px-2 py-2 text-right">Outlets</th>
              <th className="px-2 py-2 text-right">Coverage</th>
              <th className="px-2 py-2 text-right">Active months</th>
              <th className="px-2 py-2 text-right">Median volume</th>
              <th className="px-2 py-2 text-right">Cooler density</th>
              <th className="px-2 py-2 text-right">YoY</th>
              <th className="px-2 py-2 text-right">Low-risk %</th>
              <th className="px-2 py-2 text-right">Critical %</th>
              <th className="px-2 py-2">Health</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {rows.map((r: any) => (
              <tr key={r.Distributor_ID} className="hover:bg-muted/30">
                <td className="px-2 py-2 font-bold">{r.health_rank}</td>
                <td className="px-2 py-2 font-mono text-xs">
                  {r.Distributor_ID}
                </td>
                <td className="px-2 py-2 text-right">{fmtNumber(r.n_outlets)}</td>
                <td className="px-2 py-2 text-right">
                  {r.coverage_pct?.toFixed(2)}%
                </td>
                <td className="px-2 py-2 text-right">
                  {r.penetration_active_months?.toFixed(1)}
                </td>
                <td className="px-2 py-2 text-right">
                  {fmtLitres(r.median_volume_per_outlet, 1)}
                </td>
                <td className="px-2 py-2 text-right">
                  {r.cooler_density?.toFixed(2)}
                </td>
                <td className="px-2 py-2 text-right">
                  {((r.yoy_growth ?? 1) * 100 - 100).toFixed(2)}%
                </td>
                <td className="px-2 py-2 text-right">
                  {((r.low_risk_share ?? 0) * 100).toFixed(1)}%
                </td>
                <td className="px-2 py-2 text-right">
                  {((r.critical_risk_share ?? 0) * 100).toFixed(1)}%
                </td>
                <td className="px-2 py-2">
                  <div className="flex items-center gap-2">
                    <HealthBar z={r.health_z ?? 0} />
                    <span className="font-mono text-xs">
                      {(r.health_z ?? 0).toFixed(2)}
                    </span>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </CardContent>
    </Card>
  );
}
