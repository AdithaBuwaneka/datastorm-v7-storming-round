import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { api } from "@/lib/api";
import { fmtLitres, fmtNumber, fmtLKR } from "@/lib/utils";
import { PageHeader } from "@/components/page-header";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { RiskBadge } from "@/components/risk-badge";
import { AiNarrative } from "./ai-narrative";

export default async function OutletDetailPage({
  params,
}: {
  params: { id: string };
}) {
  let detail: any = null;
  let error: string | null = null;
  try {
    detail = await api.outletDetail(params.id);
  } catch (e) {
    error = e instanceof Error ? e.message : String(e);
  }

  if (!detail) {
    return (
      <>
        <BackLink />
        <PageHeader title={params.id} description="Outlet detail" />
        <Card>
          <pre className="rounded-md bg-muted p-3 text-xs">{error}</pre>
        </Card>
      </>
    );
  }

  const o = detail.outlet;
  const drivers: { direction: "positive" | "negative"; feature: string; shap: number }[] =
    detail.top_drivers || [];
  const positives = drivers.filter((d) => d.direction === "positive").slice(0, 5);
  const negatives = drivers.filter((d) => d.direction === "negative").slice(0, 5);
  const cf = detail.counterfactual || {};
  const actions = detail.recommended_actions || [];
  const roi = detail.cooler_roi || {};

  return (
    <>
      <BackLink />
      <PageHeader
        title={`${o.Outlet_ID}`}
        description={`${o.Outlet_Type} · ${o.Outlet_Size} · ${o.Province} · distributor ${o.Distributor_ID}`}
        actions={<RiskBadge band={o.risk_band} />}
      />

      <section className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Predicted potential</CardTitle>
            <CardDescription>
              January 2026 if systemic constraints were relieved.
            </CardDescription>
          </CardHeader>
          <CardContent className="grid grid-cols-2 gap-6 sm:grid-cols-4">
            <Metric label="Predicted Jan 2026" value={fmtLitres(o.Maximum_Monthly_Liters, 1)} />
            <Metric label="Recent monthly avg" value={fmtLitres(o.monthly_volume_mean, 1)} />
            <Metric label="Own Q90" value={fmtLitres(o.monthly_volume_q90, 1)} />
            <Metric label="Active months" value={`${o.active_months ?? "—"} / 36`} />
            <Metric label="Coolers" value={String(o.Cooler_Count ?? 0)} />
            <Metric
              label="Local competitors (1 km)"
              value={fmtNumber(o.competitors_1km)}
            />
            <Metric
              label="HHI (1.5 km)"
              value={fmtNumber(o.hhi_1500m, 0)}
            />
            <Metric
              label="Replenishment friction"
              value={`${((o.replenishment_friction ?? 0) * 100).toFixed(1)}%`}
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>What-if scenarios</CardTitle>
            <CardDescription>
              Model-predicted deltas if a constraint were relieved.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <DeltaRow
              label="Add one cooler"
              base={cf.base_pred}
              after={cf.cf_add_cooler}
              delta={cf.delta_add_cooler}
            />
            <DeltaRow
              label="Remove competitive drag"
              base={cf.base_pred}
              after={cf.cf_zero_competition}
              delta={cf.delta_zero_competition}
            />
            {o.Trade_Spend_LKR != null && (
              <div className="mt-4 rounded-md border border-border bg-muted/30 p-3 text-sm">
                <span className="text-muted-foreground">
                  LKR allocated for Jan 2026:
                </span>{" "}
                <span className="font-semibold">{fmtLKR(o.Trade_Spend_LKR)}</span>
              </div>
            )}
          </CardContent>
        </Card>
      </section>

      <section className="mt-6 grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Top reasons the score is high</CardTitle>
            <CardDescription>Largest positive SHAP contributors.</CardDescription>
          </CardHeader>
          <CardContent>
            <DriverList drivers={positives} positive />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Top reasons the score is held back</CardTitle>
            <CardDescription>Largest negative SHAP contributors.</CardDescription>
          </CardHeader>
          <CardContent>
            <DriverList drivers={negatives} />
          </CardContent>
        </Card>
      </section>

      <section className="mt-6">
        <Card>
          <CardHeader>
            <CardTitle>Recommended actions</CardTitle>
            <CardDescription>
              Top-3 prescriptive interventions ranked by expected monthly L uplift.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <ol className="flex flex-col gap-3">
              {actions.length === 0 && (
                <li className="text-muted-foreground">
                  No interventions surfaced for this outlet.
                </li>
              )}
              {actions.map((a: any) => (
                <li
                  key={`${a.Outlet_ID}-${a.rank}`}
                  className="rounded-md border border-border bg-card p-4"
                >
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <span className="text-xs uppercase tracking-wider text-muted-foreground">
                        Rank {a.rank} · {a.action_type}
                      </span>
                      <p className="mt-1 font-medium">{a.action}</p>
                    </div>
                    <Badge variant="success">
                      +{fmtLitres(a.predicted_uplift_L_per_month, 1)} / mo
                    </Badge>
                  </div>
                  <p className="mt-2 text-sm text-muted-foreground">{a.rationale}</p>
                </li>
              ))}
            </ol>
          </CardContent>
        </Card>
      </section>

      {roi.is_material_case ? (
        <section className="mt-6">
          <Card>
            <CardHeader>
              <CardTitle>Cooler deployment business case</CardTitle>
              <CardDescription>
                Assumes LKR 50,000 unit cost, 12% gross margin, 12% cost of capital.
              </CardDescription>
            </CardHeader>
            <CardContent className="grid grid-cols-2 gap-6 sm:grid-cols-4">
              <Metric label="Monthly uplift" value={fmtLitres(roi.monthly_uplift_L, 1)} />
              <Metric label="Monthly margin" value={fmtLKR(roi.monthly_margin_uplift_LKR)} />
              <Metric label="Payback" value={`${(roi.payback_months ?? 0).toFixed(1)} mo`} />
              <Metric label="24-mo NPV" value={fmtLKR(roi.npv_24mo_LKR)} />
            </CardContent>
          </Card>
        </section>
      ) : null}

      <section className="mt-6">
        <AiNarrative outletId={o.Outlet_ID} />
      </section>
    </>
  );
}

function BackLink() {
  return (
    <Link
      href="/outlets"
      className="mb-4 inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground"
    >
      <ArrowLeft className="h-4 w-4" /> All outlets
    </Link>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-xs uppercase tracking-wider text-muted-foreground">
        {label}
      </div>
      <div className="mt-1 text-lg font-semibold">{value}</div>
    </div>
  );
}

function DeltaRow({
  label,
  base,
  after,
  delta,
}: {
  label: string;
  base?: number;
  after?: number;
  delta?: number;
}) {
  if (after == null || base == null) {
    return (
      <div className="text-sm text-muted-foreground">
        <span className="font-medium text-foreground">{label}</span> — not available
      </div>
    );
  }
  const positive = (delta ?? 0) > 0;
  return (
    <div className="rounded-md border border-border p-3">
      <div className="flex items-center justify-between">
        <span className="font-medium">{label}</span>
        <Badge variant={positive ? "success" : "muted"}>
          {positive ? "+" : ""}
          {fmtLitres(delta, 1)} / mo
        </Badge>
      </div>
      <div className="mt-1 text-xs text-muted-foreground">
        base {fmtLitres(base, 1)} → after {fmtLitres(after, 1)}
      </div>
    </div>
  );
}

function DriverList({
  drivers,
  positive = false,
}: {
  drivers: { feature: string; shap: number }[];
  positive?: boolean;
}) {
  if (drivers.length === 0) {
    return <p className="text-sm text-muted-foreground">No drivers surfaced.</p>;
  }
  const max = Math.max(...drivers.map((d) => Math.abs(d.shap)), 1);
  return (
    <ul className="flex flex-col gap-2">
      {drivers.map((d) => {
        const width = Math.max(8, Math.round((Math.abs(d.shap) / max) * 100));
        return (
          <li key={d.feature} className="flex items-center gap-3">
            <div className="w-48 truncate font-mono text-xs">{d.feature}</div>
            <div className="relative h-2 flex-1 rounded-full bg-muted">
              <div
                className={`absolute inset-y-0 left-0 rounded-full ${
                  positive ? "bg-success" : "bg-danger"
                }`}
                style={{ width: `${width}%` }}
              />
            </div>
            <div className="w-16 text-right font-mono text-xs">
              {d.shap >= 0 ? "+" : ""}
              {fmtNumber(d.shap, 1)}
            </div>
          </li>
        );
      })}
    </ul>
  );
}
