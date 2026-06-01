"use client";

import { MapContainer, TileLayer, CircleMarker, Tooltip } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import { fmtNumber, fmtLitres } from "@/lib/utils";

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

// Sri Lanka rough centre + tight zoom that covers the four provinces
const SL_CENTER: [number, number] = [7.5, 80.8];
const ZOOM = 8;

// Colour cycle for clusters (qualitative palette)
const PALETTE = [
  "#0ea5e9",
  "#10b981",
  "#f97316",
  "#a855f7",
  "#ef4444",
  "#14b8a6",
  "#eab308",
  "#ec4899",
];

export default function TerritoryMapImpl({ clusters }: { clusters: Cluster[] }) {
  const maxN = Math.max(...clusters.map((c) => c.n_outlets), 1);
  return (
    <div className="h-[500px] overflow-hidden rounded-md border border-border">
      <MapContainer
        center={SL_CENTER}
        zoom={ZOOM}
        style={{ height: "100%", width: "100%" }}
        scrollWheelZoom
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        {clusters.map((c, idx) => {
          // Radius in pixels scaled by outlet count
          const r = 6 + Math.round((c.n_outlets / maxN) * 18);
          const color = PALETTE[idx % PALETTE.length];
          return (
            <CircleMarker
              key={c.cluster_id}
              center={[c.centroid_lat, c.centroid_lon]}
              radius={r}
              pathOptions={{
                color,
                fillColor: color,
                fillOpacity: 0.55,
                weight: 1.5,
              }}
            >
              <Tooltip direction="top" offset={[0, -4]}>
                <div className="text-xs">
                  <div className="font-semibold">Cluster #{c.cluster_id}</div>
                  <div>
                    {fmtNumber(c.n_outlets)} outlets · {c.dominant_province}
                  </div>
                  <div>
                    dominant {c.dominant_outlet_type} ·{" "}
                    {c.dominant_distributor}
                  </div>
                  <div>
                    radius {c.radius_km.toFixed(1)} km · HHI{" "}
                    {fmtNumber(c.avg_hhi_1500m, 0)}
                  </div>
                  <div>
                    total predicted{" "}
                    {fmtLitres(c.total_predicted_jan2026, 0)}
                  </div>
                </div>
              </Tooltip>
            </CircleMarker>
          );
        })}
      </MapContainer>
    </div>
  );
}
