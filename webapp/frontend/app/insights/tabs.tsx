"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import {
  Wallet,
  Snowflake,
  AlertTriangle,
  BarChart3,
  Map,
  FileText,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { VIEW_KEYS, VIEW_LABELS, type ViewKey } from "./views-config";

const ICONS: Record<ViewKey, typeof Wallet> = {
  budget: Wallet,
  "cooler-roi": Snowflake,
  dormancy: AlertTriangle,
  scorecard: BarChart3,
  territories: Map,
  forensics: FileText,
};

export function InsightTabs({ active }: { active: ViewKey }) {
  const sp = useSearchParams();
  const link = (v: string) => {
    const next = new URLSearchParams(sp?.toString() ?? "");
    next.set("view", v);
    return `/insights?${next.toString()}`;
  };
  return (
    <div className="mb-6 flex flex-wrap items-center gap-1 rounded-lg border border-border bg-card p-1">
      {VIEW_KEYS.map((key) => {
        const Icon = ICONS[key];
        const isActive = active === key;
        return (
          <Link
            key={key}
            href={link(key)}
            className={cn(
              "flex items-center gap-2 rounded-md px-3 py-2 text-sm transition-colors",
              isActive
                ? "bg-primary text-primary-foreground"
                : "text-muted-foreground hover:bg-muted hover:text-foreground",
            )}
          >
            <Icon className="h-4 w-4" />
            <span className="hidden sm:inline">{VIEW_LABELS[key]}</span>
          </Link>
        );
      })}
    </div>
  );
}
