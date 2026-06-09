import { api } from "@/lib/api";
import { PageHeader } from "@/components/page-header";
import { ShopMap } from "./shop-map";

export default async function ShopMapPage() {
  const data = await api.shopMapOutlets().catch(() => ({
    gold: [],
    silver: [] as never[],
    rejected: [],
  }));

  return (
    <>
      <PageHeader
        title="Shop Map"
        description={`${data.gold.length.toLocaleString()} outlets cleared · ${data.rejected.length.toLocaleString()} removed at DQ`}
      />
      <ShopMap gold={data.gold} rejected={data.rejected} />
    </>
  );
}
