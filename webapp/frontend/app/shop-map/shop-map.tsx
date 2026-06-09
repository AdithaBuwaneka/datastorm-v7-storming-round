"use client";

import dynamic from "next/dynamic";

export interface GoldOutlet {
  outlet_id: string;
  lat: number;
  lon: number;
  outlet_type: string | null;
  province: string | null;
}

export interface RejectedOutlet {
  outlet_id: string;
  lat: number;
  lon: number;
  outlet_type: string | null;
  rejection_reason: string | null;
  check_name: string | null;
}

interface Props {
  gold: GoldOutlet[];
  rejected: RejectedOutlet[];
}

const MapImpl = dynamic(() => import("./shop-map-impl"), {
  ssr: false,
  loading: () => (
    <div className="grid h-[600px] place-items-center rounded-md border border-border bg-muted text-sm text-muted-foreground">
      Loading map…
    </div>
  ),
});

export function ShopMap({ gold, rejected }: Props) {
  return <MapImpl gold={gold} rejected={rejected} />;
}
