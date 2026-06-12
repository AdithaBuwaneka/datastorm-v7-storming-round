import {
  Store,
  Droplets,
  Wallet,
  AlertTriangle,
  Snowflake,
  TrendingUp,
} from "lucide-react";
import { api } from "@/lib/api";
import type { Summary } from "@/lib/types";
import { fmtLKR, fmtLitres, fmtNumber } from "@/lib/utils";
import { KpiTile } from "@/components/kpi-tile";
import { PageHeader } from "@/components/page-header";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import {
  ProvinceBarChart,
  DormancyDonut,
  ChannelDonut,
} from "@/components/dashboard-charts";

export default async function DashboardPage() {
  let summary: Summary | null = null;
  let error: string | null = null;
  let bands: Record<string, number> = {};
  let channelTotals: Record<string, number> = {};
  try {
    const [s, b, ch] = await Promise.all([
      api.summary() as unknown as Promise<Summary>,
      api.dormancyBands().catch(() => ({})),
      api.budgetByChannel().catch(() => ({ totals: {}, rows: [] })),
    ]);
    summary = s;
    bands = b as Record<string, number>;
    channelTotals = (ch as { totals: Record<string, number> }).totals || {};
  } catch (e) {
    error = e instanceof Error ? e.message : String(e);
  }

  if (!summary) {
    return (
      <>
        <PageHeader title="Dashboard" description="Outlet potential overview" />
        <Card>
          <CardHeader>
            <CardTitle>Backend not reachable</CardTitle>
            <CardDescription>
              Could not call the FastAPI service at {process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8000"}.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <pre className="rounded-md bg-muted p-3 text-xs">{error}</pre>
            <p className="mt-3 text-sm text-muted-foreground">
              Start the backend with{" "}
              <code className="rounded bg-muted px-1.5 py-0.5">
                uvicorn webapp.backend.main:app --port 8000
              </code>
              .
            </p>
          </CardContent>
        </Card>
      </>
    );
  }

  return (
    <>
      <PageHeader
        title="Dashboard"
        description="January 2026 outlet potential and decision-support summary"
      />

      <section className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <KpiTile
          label="Outlets covered"
          value={fmtNumber(summary.n_outlets)}
          sublabel="across 4 provinces"
          icon={Store}
        />
        <KpiTile
          label="Total predicted Jan 2026"
          value={fmtLitres(summary.total_predicted_jan2026_L)}
          sublabel={`median ${fmtLitres(summary.median_predicted_jan2026_L, 1)} per outlet`}
          icon={Droplets}
          accent="success"
        />
        <KpiTile
          label="LKR 5M allocated"
          value={fmtLKR(summary.budget_allocated_LKR)}
          sublabel="Western Province · LKR 5M cap"
          icon={Wallet}
          accent="warning"
        />
        <KpiTile
          label="High / critical risk"
          value={fmtNumber(summary.outlets_high_or_critical_risk)}
          sublabel="dormancy early-warning"
          icon={AlertTriangle}
          accent="danger"
        />
        <KpiTile
          label="Cooler Top-100 capex"
          value={fmtLKR(summary.cooler_top100_capex_LKR)}
          sublabel="LKR 50,000 unit cost"
          icon={Snowflake}
        />
        <KpiTile
          label="24-month margin uplift"
          value={fmtLKR(summary.cooler_top100_24mo_margin_LKR)}
          sublabel="from Top-100 cooler deployment"
          icon={TrendingUp}
          accent="success"
        />
      </section>

      <section className="mt-8 grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Outlets by province</CardTitle>
            <CardDescription>
              Total active outlets across the four covered provinces.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <ProvinceBarChart
              data={Object.entries(summary.outlets_by_province).map(
                ([name, value]) => ({ name, value: value as number }),
              )}
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Dormancy risk distribution</CardTitle>
            <CardDescription>
              Outlets by predicted lapse-risk band (early-warning classifier).
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
      </section>

      <section className="mt-6 grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>LKR 5M trade-spend by channel</CardTitle>
            <CardDescription>
              Western Province allocation split across discount, merchandising
              and promotional spend.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <ChannelDonut
              data={[
                { name: "Discount", value: channelTotals.Discount_LKR ?? 0 },
                {
                  name: "Merchandising",
                  value: channelTotals.Merchandising_LKR ?? 0,
                },
                {
                  name: "Promotional",
                  value: channelTotals.Promotional_LKR ?? 0,
                },
              ].filter((d) => d.value > 0)}
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>What&apos;s next</CardTitle>
            <CardDescription>
              Direct paths into the decision tools.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <ul className="flex flex-col gap-2 text-sm">
              <li>
                <a className="text-primary underline-offset-4 hover:underline" href="/outlets">
                  Browse all 20,000 outlets →
                </a>
              </li>
              <li>
                <a className="text-primary underline-offset-4 hover:underline" href="/insights?view=budget">
                  Inspect the LKR 5M trade-spend allocation →
                </a>
              </li>
              <li>
                <a className="text-primary underline-offset-4 hover:underline" href="/insights?view=cooler-roi">
                  Review the Top-100 cooler deployment ROI →
                </a>
              </li>
              <li>
                <a className="text-primary underline-offset-4 hover:underline" href="/insights?view=dormancy">
                  Surface high-risk outlets for sales intervention →
                </a>
              </li>
              <li>
                <a className="text-primary underline-offset-4 hover:underline" href="/insights?view=scorecard">
                  Compare distributor operational health →
                </a>
              </li>
              <li>
                <a className="text-primary underline-offset-4 hover:underline" href="/insights?view=territories">
                  Explore sales territories on the map →
                </a>
              </li>
              <li>
                <a className="text-primary underline-offset-4 hover:underline" href="/insights?view=forensics">
                  Audit data-forensics findings →
                </a>
              </li>
            </ul>
          </CardContent>
        </Card>
      </section>
    </>
  );
}
