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

export default async function DashboardPage() {
  let summary: Summary | null = null;
  let error: string | null = null;
  try {
    summary = (await api.summary()) as unknown as Summary;
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

      <section className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
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
            <ul className="flex flex-col divide-y divide-border">
              {Object.entries(summary.outlets_by_province).map(([prov, n]) => (
                <li
                  key={prov}
                  className="flex items-center justify-between py-2"
                >
                  <span className="font-medium">{prov}</span>
                  <span className="text-muted-foreground">
                    {fmtNumber(n as number)} outlets
                  </span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>What's next</CardTitle>
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
