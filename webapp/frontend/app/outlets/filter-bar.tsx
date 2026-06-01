"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useState, useTransition } from "react";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Button } from "@/components/ui/button";

interface FilterOptions {
  provinces: string[];
  distributors: string[];
  outlet_types: string[];
  outlet_sizes: string[];
  risk_bands: string[];
}

export function FilterBar({ filters }: { filters: FilterOptions }) {
  const router = useRouter();
  const sp = useSearchParams();
  const [pending, startTransition] = useTransition();
  const [search, setSearch] = useState(sp.get("search") ?? "");

  function push(key: string, value: string) {
    const params = new URLSearchParams(sp.toString());
    if (value) params.set(key, value);
    else params.delete(key);
    params.delete("page"); // reset paging when filters change
    startTransition(() => router.push(`/outlets?${params.toString()}`));
  }

  return (
    <div className="grid grid-cols-1 gap-3 rounded-lg border border-border bg-card p-4 sm:grid-cols-2 lg:grid-cols-6">
      <div className="flex flex-col gap-1">
        <label className="text-xs font-medium text-muted-foreground">
          Search Outlet_ID
        </label>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            push("search", search);
          }}
        >
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="OUT_12345"
          />
        </form>
      </div>

      <SelectField
        label="Province"
        defaultValue={sp.get("province") ?? ""}
        options={filters.provinces}
        onChange={(v) => push("province", v)}
      />
      <SelectField
        label="Distributor"
        defaultValue={sp.get("distributor") ?? ""}
        options={filters.distributors}
        onChange={(v) => push("distributor", v)}
      />
      <SelectField
        label="Outlet type"
        defaultValue={sp.get("outlet_type") ?? ""}
        options={filters.outlet_types}
        onChange={(v) => push("outlet_type", v)}
      />
      <SelectField
        label="Outlet size"
        defaultValue={sp.get("outlet_size") ?? ""}
        options={filters.outlet_sizes}
        onChange={(v) => push("outlet_size", v)}
      />
      <SelectField
        label="Dormancy risk"
        defaultValue={sp.get("risk_band") ?? ""}
        options={filters.risk_bands}
        onChange={(v) => push("risk_band", v)}
      />

      <div className="col-span-full flex items-center justify-end gap-2 pt-2">
        <span className="text-xs text-muted-foreground">
          {pending ? "Loading…" : null}
        </span>
        <Button
          variant="outline"
          size="sm"
          onClick={() => router.push("/outlets")}
        >
          Clear filters
        </Button>
      </div>
    </div>
  );
}

function SelectField({
  label,
  defaultValue,
  options,
  onChange,
}: {
  label: string;
  defaultValue: string;
  options: string[];
  onChange: (v: string) => void;
}) {
  return (
    <div className="flex flex-col gap-1">
      <label className="text-xs font-medium text-muted-foreground">{label}</label>
      <Select
        defaultValue={defaultValue}
        onChange={(e) => onChange(e.target.value)}
      >
        <option value="">All</option>
        {options.map((o) => (
          <option key={o} value={o}>
            {o}
          </option>
        ))}
      </Select>
    </div>
  );
}
