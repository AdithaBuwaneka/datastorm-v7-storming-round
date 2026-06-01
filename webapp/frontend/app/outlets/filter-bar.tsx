"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useState, useTransition } from "react";
import { X } from "lucide-react";
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
    params.delete("page");
    startTransition(() => router.push(`/outlets?${params.toString()}`));
  }

  const hasActive =
    Array.from(sp.entries()).filter(([k]) => k !== "page").length > 0;

  return (
    <div className="flex flex-wrap items-end gap-2 rounded-lg border border-border bg-card px-3 py-2">
      <Field label="Search">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            push("search", search);
          }}
        >
          <Input
            className="h-8 w-36 text-xs"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="OUT_12345"
          />
        </form>
      </Field>

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
        label="Type"
        defaultValue={sp.get("outlet_type") ?? ""}
        options={filters.outlet_types}
        onChange={(v) => push("outlet_type", v)}
      />
      <SelectField
        label="Size"
        defaultValue={sp.get("outlet_size") ?? ""}
        options={filters.outlet_sizes}
        onChange={(v) => push("outlet_size", v)}
      />
      <SelectField
        label="Risk"
        defaultValue={sp.get("risk_band") ?? ""}
        options={filters.risk_bands}
        onChange={(v) => push("risk_band", v)}
      />

      <div className="ml-auto flex items-center gap-2">
        {pending && (
          <span className="text-xs text-muted-foreground">Loading…</span>
        )}
        {hasActive && (
          <Button
            variant="ghost"
            size="sm"
            className="h-8 gap-1 text-xs"
            onClick={() => router.push("/outlets")}
          >
            <X className="h-3 w-3" />
            Clear
          </Button>
        )}
      </div>
    </div>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-0.5">
      <label className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
        {label}
      </label>
      {children}
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
    <Field label={label}>
      <Select
        className="h-8 w-32 text-xs"
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
    </Field>
  );
}
