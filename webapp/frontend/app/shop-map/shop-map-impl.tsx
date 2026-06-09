"use client";

import { useState, useMemo } from "react";
import { MapContainer, TileLayer, CircleMarker, Tooltip } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import type { GoldOutlet, RejectedOutlet } from "./shop-map";

const SL_CENTER: [number, number] = [7.5, 80.8];
const ZOOM = 8;

// Map raw rejection reasons to a data-lake level (silver vs bronze)
function rejectionLevel(reason: string | null): "silver" | "bronze" {
  if (!reason) return "bronze";
  if (reason.includes("Land-mask outlier")) return "silver";
  return "bronze";
}

// Human-readable label for the three failure reasons present in this pipeline
const REASON_LABELS: Record<string, string> = {
  "Land-mask outlier (>= 5.0 km from nearest land outlet)": "Sea/land-mask outlier",
  "Latitude outside [5.9, 9.9] (inclusive=True)": "Latitude outside Sri Lanka",
  "Outlet_ID not in reference set": "Reference set mismatch",
};

function labelReason(r: string | null): string {
  if (!r) return "Unknown";
  return REASON_LABELS[r] ?? r;
}

interface Props {
  gold: GoldOutlet[];
  rejected: RejectedOutlet[];
}

export default function ShopMapImpl({ gold, rejected }: Props) {
  const [showGold, setShowGold] = useState(true);
  const [showSilver, setShowSilver] = useState(true);
  const [showBronze, setShowBronze] = useState(true);

  const silverRejected = useMemo(
    () => rejected.filter((r) => rejectionLevel(r.rejection_reason) === "silver"),
    [rejected],
  );
  const bronzeRejected = useMemo(
    () => rejected.filter((r) => rejectionLevel(r.rejection_reason) === "bronze"),
    [rejected],
  );

  // Per-reason sub-filter inside each level
  const allSilverReasons = useMemo(() => {
    const s = new Set<string>();
    silverRejected.forEach((r) => s.add(labelReason(r.rejection_reason)));
    return Array.from(s).sort();
  }, [silverRejected]);

  const allBronzeReasons = useMemo(() => {
    const s = new Set<string>();
    bronzeRejected.forEach((r) => s.add(labelReason(r.rejection_reason)));
    return Array.from(s).sort();
  }, [bronzeRejected]);

  const [activeSilverReasons, setActiveSilverReasons] = useState<Set<string>>(
    () => new Set(allSilverReasons),
  );
  const [activeBronzeReasons, setActiveBronzeReasons] = useState<Set<string>>(
    () => new Set(allBronzeReasons),
  );

  function toggleSilverReason(r: string) {
    setActiveSilverReasons((prev) => {
      const next = new Set(prev);
      if (next.has(r)) next.delete(r);
      else next.add(r);
      return next;
    });
  }
  function toggleBronzeReason(r: string) {
    setActiveBronzeReasons((prev) => {
      const next = new Set(prev);
      if (next.has(r)) next.delete(r);
      else next.add(r);
      return next;
    });
  }

  const visibleSilver = useMemo(
    () =>
      showSilver
        ? silverRejected.filter((r) =>
            activeSilverReasons.has(labelReason(r.rejection_reason)),
          )
        : [],
    [silverRejected, showSilver, activeSilverReasons],
  );

  const visibleBronze = useMemo(
    () =>
      showBronze
        ? bronzeRejected.filter((r) =>
            activeBronzeReasons.has(labelReason(r.rejection_reason)),
          )
        : [],
    [bronzeRejected, showBronze, activeBronzeReasons],
  );

  const totalShown =
    (showGold ? gold.length : 0) + visibleSilver.length + visibleBronze.length;

  return (
    <div className="flex h-[calc(100vh-10rem)] gap-4">
      {/* Sidebar controls */}
      <aside className="w-64 shrink-0 overflow-y-auto rounded-md border border-border bg-card p-4 text-sm">
        {/* Gold layer */}
        <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          Data Lake Levels
        </p>

        <label className="flex cursor-pointer items-center gap-2 py-1">
          <input
            type="checkbox"
            className="h-4 w-4 rounded accent-emerald-500"
            checked={showGold}
            onChange={(e) => setShowGold(e.target.checked)}
          />
          <span className="inline-block h-3 w-3 shrink-0 rounded-full bg-emerald-500" />
          <span>
            Gold{" "}
            <span className="text-muted-foreground">
              ({gold.length.toLocaleString()})
            </span>
          </span>
        </label>

        {/* Silver layer — land-mask failures (passed lat check, removed at sea check) */}
        <label className="flex cursor-pointer items-center gap-2 py-1">
          <input
            type="checkbox"
            className="h-4 w-4 rounded accent-blue-500"
            checked={showSilver}
            onChange={(e) => setShowSilver(e.target.checked)}
          />
          <span className="inline-block h-3 w-3 shrink-0 rounded-full bg-blue-500" />
          <span>
            Silver removed{" "}
            <span className="text-muted-foreground">
              ({silverRejected.length.toLocaleString()})
            </span>
          </span>
        </label>

        {showSilver && allSilverReasons.length > 0 && (
          <div className="ml-6 mt-1 space-y-0.5">
            {allSilverReasons.map((reason) => {
              const count = silverRejected.filter(
                (r) => labelReason(r.rejection_reason) === reason,
              ).length;
              return (
                <label key={reason} className="flex cursor-pointer items-start gap-1.5 py-0.5 text-xs">
                  <input
                    type="checkbox"
                    className="mt-0.5 h-3.5 w-3.5 shrink-0 rounded accent-blue-500"
                    checked={activeSilverReasons.has(reason)}
                    onChange={() => toggleSilverReason(reason)}
                  />
                  <span>
                    {reason}{" "}
                    <span className="text-muted-foreground">({count})</span>
                  </span>
                </label>
              );
            })}
          </div>
        )}

        {/* Bronze layer — lat-range + ref failures */}
        <label className="mt-1 flex cursor-pointer items-center gap-2 py-1">
          <input
            type="checkbox"
            className="h-4 w-4 rounded accent-orange-500"
            checked={showBronze}
            onChange={(e) => setShowBronze(e.target.checked)}
          />
          <span className="inline-block h-3 w-3 shrink-0 rounded-full bg-orange-500" />
          <span>
            Bronze removed{" "}
            <span className="text-muted-foreground">
              ({bronzeRejected.length.toLocaleString()})
            </span>
          </span>
        </label>

        {showBronze && allBronzeReasons.length > 0 && (
          <div className="ml-6 mt-1 space-y-0.5">
            {allBronzeReasons.map((reason) => {
              const count = bronzeRejected.filter(
                (r) => labelReason(r.rejection_reason) === reason,
              ).length;
              return (
                <label key={reason} className="flex cursor-pointer items-start gap-1.5 py-0.5 text-xs">
                  <input
                    type="checkbox"
                    className="mt-0.5 h-3.5 w-3.5 shrink-0 rounded accent-orange-500"
                    checked={activeBronzeReasons.has(reason)}
                    onChange={() => toggleBronzeReason(reason)}
                  />
                  <span>
                    {reason}{" "}
                    <span className="text-muted-foreground">({count})</span>
                  </span>
                </label>
              );
            })}
          </div>
        )}

        {/* Legend / stats */}
        <div className="mt-5 border-t border-border pt-4 text-xs text-muted-foreground">
          <p className="font-medium text-foreground">Legend</p>
          <p className="mt-1">
            <span className="font-semibold text-emerald-500">Green</span> — cleared all
            pipeline stages
          </p>
          <p className="mt-1">
            <span className="font-semibold text-blue-500">Blue</span> — removed at silver
            sea-coordinate check
          </p>
          <p className="mt-1">
            <span className="font-semibold text-orange-400">Orange</span> — removed at
            bronze/lat check
          </p>
          <p className="mt-3">
            Visible:{" "}
            <span className="font-medium text-foreground">
              {totalShown.toLocaleString()}
            </span>
          </p>
        </div>
      </aside>

      {/* Map */}
      <div className="flex-1 overflow-hidden rounded-md border border-border">
        <MapContainer
          center={SL_CENTER}
          zoom={ZOOM}
          style={{ height: "100%", width: "100%" }}
          scrollWheelZoom
          preferCanvas
        >
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/">OpenStreetMap</a> contributors'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />

          {/* Gold outlets */}
          {showGold &&
            gold.map((o) => (
              <CircleMarker
                key={o.outlet_id}
                center={[o.lat, o.lon]}
                radius={3}
                pathOptions={{
                  color: "#10b981",
                  fillColor: "#10b981",
                  fillOpacity: 0.55,
                  weight: 0.5,
                }}
              >
                <Tooltip direction="top" offset={[0, -4]}>
                  <div className="text-xs">
                    <div className="font-semibold">{o.outlet_id}</div>
                    <div>
                      {o.outlet_type ?? "—"} · {o.province ?? "—"}
                    </div>
                    <div className="font-medium text-emerald-600">Gold layer</div>
                  </div>
                </Tooltip>
              </CircleMarker>
            ))}

          {/* Silver-removed outlets (land-mask failures) */}
          {visibleSilver.map((o) => (
            <CircleMarker
              key={o.outlet_id}
              center={[o.lat, o.lon]}
              radius={4}
              pathOptions={{
                color: "#3b82f6",
                fillColor: "#3b82f6",
                fillOpacity: 0.75,
                weight: 1,
              }}
            >
              <Tooltip direction="top" offset={[0, -4]}>
                <div className="text-xs">
                  <div className="font-semibold">{o.outlet_id}</div>
                  <div>{o.outlet_type ?? "—"}</div>
                  <div className="font-medium text-blue-600">
                    Silver removed: {labelReason(o.rejection_reason)}
                  </div>
                </div>
              </Tooltip>
            </CircleMarker>
          ))}

          {/* Bronze-removed outlets (lat-range / ref failures) */}
          {visibleBronze.map((o) => (
            <CircleMarker
              key={o.outlet_id}
              center={[o.lat, o.lon]}
              radius={4}
              pathOptions={{
                color: "#f97316",
                fillColor: "#f97316",
                fillOpacity: 0.75,
                weight: 1,
              }}
            >
              <Tooltip direction="top" offset={[0, -4]}>
                <div className="text-xs">
                  <div className="font-semibold">{o.outlet_id}</div>
                  <div>{o.outlet_type ?? "—"}</div>
                  <div className="font-medium text-orange-600">
                    Bronze removed: {labelReason(o.rejection_reason)}
                  </div>
                </div>
              </Tooltip>
            </CircleMarker>
          ))}
        </MapContainer>
      </div>
    </div>
  );
}
