import { Badge } from "@/components/ui/badge";
import type { RiskBand } from "@/lib/types";

const map: Record<RiskBand, { label: string; variant: "success" | "warning" | "danger" | "muted" }> = {
  low: { label: "Low", variant: "success" },
  moderate: { label: "Moderate", variant: "muted" },
  high: { label: "High", variant: "warning" },
  critical: { label: "Critical", variant: "danger" },
};

export function RiskBadge({ band }: { band: RiskBand | null | undefined }) {
  if (!band) return <Badge variant="muted">—</Badge>;
  const meta = map[band] ?? map.moderate;
  return <Badge variant={meta.variant}>{meta.label}</Badge>;
}
