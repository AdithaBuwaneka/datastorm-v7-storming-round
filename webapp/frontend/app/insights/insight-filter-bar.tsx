"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useState, useTransition } from "react";
import { X, ArrowUpDown, ArrowUp, ArrowDown } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Button } from "@/components/ui/button";

export interface FilterConfig {
  key: string;
  label: string;
  options: { label: string; value: string }[];
}

export function InsightFilterBar({ filters }: { filters: FilterConfig[] }) {
  const router = useRouter();
  const sp = useSearchParams();
  const [pending, startTransition] = useTransition();
  const [search, setSearch] = useState(sp.get("search") ?? "");

  function push(key: string, value: string) {
    const params = new URLSearchParams(sp.toString());
    if (value) params.set(key, value);
    else params.delete(key);
    params.delete("page");
    startTransition(() => router.push(`/insights?${params.toString()}`));
  }

  const hasSearch = !!sp.get("search");
  const hasActive =
    Array.from(sp.entries()).filter(([k]) => k !== "page" && k !== "view").length > 0;

  return (
    <div className="mt-4 flex flex-wrap items-end gap-2 rounded-lg border border-border bg-card px-3 py-2">
      <div className="flex shrink-0 flex-col gap-0.5">
        <label className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
          Search Outlets
        </label>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            push("search", search);
          }}
        >
          <Input
            className="h-8 w-32 text-xs md:w-48"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="OUT_12345"
          />
        </form>
      </div>

      {filters.map((f) => (
        <div key={f.key} className="flex shrink-0 flex-col gap-0.5">
          <label className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
            {f.label}
          </label>
          <Select
            className="h-8 w-28 text-xs md:w-32"
            value={sp.get(f.key) ?? ""}
            onChange={(e) => push(f.key, e.target.value)}
          >
            <option value="">All</option>
            {f.options.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </Select>
        </div>
      ))}

      <div className="ml-auto flex h-8 shrink-0 items-center gap-2 self-end">
        <span
          className={`text-xs text-muted-foreground transition-opacity ${
            pending ? "opacity-100" : "opacity-0"
          }`}
        >
          Loading…
        </span>
        <Button
          variant="ghost"
          size="sm"
          className={`h-8 gap-1 text-xs ${hasActive ? "" : "invisible"}`}
          onClick={() => {
            setSearch("");
            const params = new URLSearchParams(sp.toString());
            const view = params.get("view");
            const newParams = new URLSearchParams();
            if (view) newParams.set("view", view);
            startTransition(() => router.push(`/insights?${newParams.toString()}`));
          }}
        >
          <X className="h-3 w-3" />
          Clear
        </Button>
      </div>
    </div>
  );
}

export function SortableHeader({
  field,
  label,
  className,
}: {
  field: string;
  label: string;
  className?: string;
}) {
  const router = useRouter();
  const sp = useSearchParams();
  
  const currentSort = sp.get("sort_by");
  const currentDesc = sp.get("descending") === "true";

  const isCurrent = currentSort === field;

  function onClick() {
    const params = new URLSearchParams(sp.toString());
    params.delete("page");
    if (isCurrent) {
      if (currentDesc) {
        params.delete("sort_by");
        params.delete("descending");
      } else {
        params.set("descending", "true");
      }
    } else {
      params.set("sort_by", field);
      params.delete("descending"); // Default to asc
    }
    router.push(`/insights?${params.toString()}`);
  }

  return (
    <th
      className={`cursor-pointer whitespace-nowrap hover:bg-muted/30 transition-colors ${className}`}
      onClick={onClick}
    >
      <div className={`flex items-center gap-1 ${className?.includes('text-right') ? 'justify-end' : className?.includes('text-center') ? 'justify-center' : ''}`}>
        {label}
        {isCurrent ? (
          currentDesc ? <ArrowDown className="h-3 w-3" /> : <ArrowUp className="h-3 w-3" />
        ) : (
          <ArrowUpDown className="h-3 w-3 opacity-20" />
        )}
      </div>
    </th>
  );
}
