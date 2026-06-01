"use client";

import dynamic from "next/dynamic";
import "leaflet/dist/leaflet.css";

interface Cluster {
  cluster_id: number;
  n_outlets: number;
  centroid_lat: number;
  centroid_lon: number;
  radius_km: number;
  dominant_province: string;
  dominant_outlet_type: string;
  dominant_distributor: string;
  total_predicted_jan2026: number;
  avg_hhi_1500m: number;
}

// Leaflet pulls window/document on import, so we client-only it
const MapImpl = dynamic(() => import("./territory-map-impl"), {
  ssr: false,
  loading: () => (
    <div className="grid h-[500px] place-items-center rounded-md border border-border bg-muted text-sm text-muted-foreground">
      Loading map…
    </div>
  ),
});

export function TerritoryMap({ clusters }: { clusters: Cluster[] }) {
  return <MapImpl clusters={clusters} />;
}
