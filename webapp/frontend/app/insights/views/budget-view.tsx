import { api } from "@/lib/api";
import { fmtLKR, fmtNumber } from "@/lib/utils";
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
} from "@/components/ui/card";
import { KpiTile } from "@/components/kpi-tile";
import { Wallet, Megaphone, Tag, Sparkles } from "lucide-react";

export async function BudgetView() {
  const [byDist, byCh, topOutlets] = await Promise.all([
    api.budgetByDistributor(),
    api.budgetByChannel(),
    api.budgetOutlets(50),
  ]);

  const totals = byCh.totals || {};
  const total = totals["Total_LKR"] ?? 5_000_000;
  const distSorted = [...byDist].sort(
    (a, b) => (b.total_spend_LKR || 0) - (a.total_spend_LKR || 0),
  );
  const distMax = Math.max(...distSorted.map((d) => d.total_spend_LKR || 0), 1);

  const channels = [
    { label: "Discount", key: "Discount_LKR", icon: Tag, accent: "warning" as const },
    { label: "Merchandising", key: "Merchandising_LKR", icon: Megaphone, accent: "primary" as const },
    { label: "Promotional", key: "Promotional_LKR", icon: Sparkles, accent: "success" as const },
  ];

  return (
    <>
      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <KpiTile
          label="Total allocated"
          value={fmtLKR(total)}
          sublabel="LKR 5,000,000 cap"
          icon={Wallet}
        />
        {channels.map(({ label, key, icon, accent }) => (
          <KpiTile
            key={key}
            label={label}
            value={fmtLKR(totals[key] as number)}
            sublabel={
              total > 0
                ? `${(((totals[key] as number) / total) * 100).toFixed(1)}% of total`
                : undefined
            }
            icon={icon}
            accent={accent}
          />
        ))}
      </section>

      <section className="mt-6 grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>By distributor</CardTitle>
            <CardDescription>
              Total LKR allocated to each Western Province distributor and
              their share of the LKR 5M budget.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <ul className="flex flex-col gap-2">
              {distSorted.map((d) => {
                const share = (d.total_spend_LKR / distMax) * 100;
                return (
                  <li key={d.Distributor_ID} className="flex flex-col gap-1">
                    <div className="flex items-center justify-between text-sm">
                      <span className="font-mono">{d.Distributor_ID}</span>
                      <span>
                        {fmtLKR(d.total_spend_LKR)} ·{" "}
                        <span className="text-muted-foreground">
                          {d.pct_of_budget}%
                        </span>
                      </span>
                    </div>
                    <div className="h-2 rounded-full bg-muted">
                      <div
                        className="h-full rounded-full bg-primary"
                        style={{ width: `${share}%` }}
                      />
                    </div>
                    <span className="text-xs text-muted-foreground">
                      {fmtNumber(d.n_outlets)} outlets · median{" "}
                      {fmtLKR(d.median_spend_LKR)}
                    </span>
                  </li>
                );
              })}
            </ul>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Top 50 outlets by allocation</CardTitle>
            <CardDescription>
              The outlets receiving the largest individual LKR shares.
            </CardDescription>
          </CardHeader>
          <CardContent className="max-h-[480px] overflow-y-auto">
            <table className="w-full text-sm">
              <thead className="text-left text-xs uppercase tracking-wider text-muted-foreground">
                <tr>
                  <th className="px-2 py-2">Outlet</th>
                  <th className="px-2 py-2 text-right">Trade spend</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {topOutlets.map((o: any) => (
                  <tr key={o.Outlet_ID}>
                    <td className="px-2 py-2 font-mono text-xs">{o.Outlet_ID}</td>
                    <td className="px-2 py-2 text-right">
                      {fmtLKR(o.Trade_Spend_LKR)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
      </section>
    </>
  );
}
