"use client";

import dynamic from "next/dynamic";

const OutletMapImpl = dynamic(() => import("./outlet-map-impl"), {
  ssr: false,
  loading: () => <div className="h-[300px] w-full animate-pulse rounded-md border border-border bg-muted" />,
});

export function OutletMap({ lat, lng, title }: { lat: number; lng: number; title: string }) {
  if (lat == null || lng == null) return null;
  return <OutletMapImpl lat={lat} lng={lng} title={title} />;
}
