import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import type { LucideIcon } from "lucide-react";

interface KpiTileProps {
  label: string;
  value: string;
  sublabel?: string;
  icon?: LucideIcon;
  accent?: "primary" | "success" | "warning" | "danger" | "muted";
  className?: string;
}

const accentBg = {
  primary: "bg-primary/10 text-primary",
  success: "bg-success/10 text-success",
  warning: "bg-warning/10 text-warning",
  danger: "bg-danger/10 text-danger",
  muted: "bg-muted text-muted-foreground",
};

export function KpiTile({
  label,
  value,
  sublabel,
  icon: Icon,
  accent = "primary",
  className,
}: KpiTileProps) {
  return (
    <Card className={cn("flex items-start justify-between gap-4", className)}>
      <div className="flex flex-col gap-1">
        <span className="text-xs uppercase tracking-wider text-muted-foreground">
          {label}
        </span>
        <span className="text-2xl font-bold leading-tight">{value}</span>
        {sublabel && (
          <span className="text-xs text-muted-foreground">{sublabel}</span>
        )}
      </div>
      {Icon && (
        <div
          className={cn(
            "rounded-md p-2",
            accentBg[accent],
          )}
        >
          <Icon className="h-5 w-5" />
        </div>
      )}
    </Card>
  );
}
