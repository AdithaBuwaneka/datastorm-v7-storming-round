import { api } from "@/lib/api";
import { fmtNumber, fmtLitres } from "@/lib/utils";
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
} from "@/components/ui/card";
import { TerritoryMap } from "./territory-map";
import { PaginationBar, buildPageHref } from "@/components/pagination-bar";

const PAGE_SIZE = 20;

export async function TerritoriesView({ page = 1 }: { page?: number }) {
  const rows = await api.territories();
  const totalPages = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
  const safePage = Math.min(Math.max(1, page), totalPages);
  const start = (safePage - 1) * PAGE_SIZE;
  const slice = rows.slice(start, start + PAGE_SIZE);
  return (
    <>
      <Card className="mb-6">
        <CardHeader>
          <CardTitle>Sales territories (HDBSCAN)</CardTitle>
          <CardDescription>
            96 sub-province territories derived by density-based clustering of
            outlet coordinates (haversine metric, leaf selection). Useful for
            route planning and per-territory campaign targeting.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <TerritoryMap clusters={rows as any[]} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Cluster summary</CardTitle>
          <CardDescription>
            Ranked by total predicted Jan 2026 potential.
          </CardDescription>
        </CardHeader>
        <CardContent className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-xs uppercase tracking-wider text-muted-foreground">
              <tr>
                <th className="px-2 py-2">Cluster</th>
                <th className="px-2 py-2 text-right">Outlets</th>
                <th className="px-2 py-2">Province</th>
                <th className="px-2 py-2">Dominant type</th>
                <th className="px-2 py-2">Distributor</th>
                <th className="px-2 py-2 text-right">Radius (km)</th>
                <th className="px-2 py-2 text-right">Total potential</th>
                <th className="px-2 py-2 text-right">Avg HHI</th>
                <th className="px-2 py-2 text-right">Avg competitors / km</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {slice.map((r: any) => (
                <tr key={r.cluster_id} className="hover:bg-muted/30">
                  <td className="px-2 py-2 font-mono">#{r.cluster_id}</td>
                  <td className="px-2 py-2 text-right">{fmtNumber(r.n_outlets)}</td>
                  <td className="px-2 py-2">{r.dominant_province}</td>
                  <td className="px-2 py-2">{r.dominant_outlet_type}</td>
                  <td className="px-2 py-2 font-mono text-xs">
                    {r.dominant_distributor}
                  </td>
                  <td className="px-2 py-2 text-right">
                    {r.radius_km?.toFixed(2)}
                  </td>
                  <td className="px-2 py-2 text-right font-semibold">
                    {fmtLitres(r.total_predicted_jan2026, 0)}
                  </td>
                  <td className="px-2 py-2 text-right">
                    {fmtNumber(r.avg_hhi_1500m, 0)}
                  </td>
                  <td className="px-2 py-2 text-right">
                    {r.avg_competitors_1km?.toFixed(1)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <PaginationBar
            page={safePage}
            totalPages={totalPages}
            totalRows={rows.length}
            label="territories"
            pageHref={(p) => buildPageHref("/insights", "territories", p)}
          />
        </CardContent>
      </Card>
    </>
  );
}
