import { api } from "@/lib/api";
import { fmtNumber } from "@/lib/utils";
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

const treatmentVariant: Record<string, "success" | "warning" | "muted" | "danger"> = {
  cleaned: "success",
  cleaned_and_flagged: "success",
  flagged: "warning",
  flagged_for_modeling: "warning",
  reported_clean: "muted",
  none_found: "muted",
  quarantined: "danger",
};

export async function ForensicsView() {
  const rows = await api.forensics();
  return (
    <Card>
      <CardHeader>
        <CardTitle>Forensic findings</CardTitle>
        <CardDescription>
          Beyond-DQ artefacts surfaced by the silver-clean + forensics layer.
          These describe how the team neutralised legacy SFA / ERP issues
          before any modelling ran.
        </CardDescription>
      </CardHeader>
      <CardContent className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-left text-xs uppercase tracking-wider text-muted-foreground">
            <tr>
              <th className="px-2 py-2">Finding</th>
              <th className="px-2 py-2 text-right">Count</th>
              <th className="px-2 py-2">Treatment</th>
              <th className="px-2 py-2">Detail</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {rows.map((r: any, i: number) => (
              <tr key={i}>
                <td className="px-2 py-2">{r.finding}</td>
                <td className="px-2 py-2 text-right font-mono">
                  {fmtNumber(r.count)}
                </td>
                <td className="px-2 py-2">
                  <Badge variant={treatmentVariant[r.treatment] || "muted"}>
                    {(r.treatment || "").replace(/_/g, " ")}
                  </Badge>
                </td>
                <td className="px-2 py-2 max-w-[480px] text-xs text-muted-foreground">
                  {r.detail || ""}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </CardContent>
    </Card>
  );
}
