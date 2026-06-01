import { PageHeader } from "@/components/page-header";
import { InsightTabs } from "./tabs";
import { VIEW_KEYS, type ViewKey } from "./views-config";
import { BudgetView } from "./views/budget-view";
import { CoolerRoiView } from "./views/cooler-roi-view";
import { DormancyView } from "./views/dormancy-view";
import { ScorecardView } from "./views/scorecard-view";
import { TerritoriesView } from "./views/territories-view";
import { ForensicsView } from "./views/forensics-view";

type Search = Record<string, string | string[] | undefined>;

const TITLES: Record<ViewKey, { title: string; desc: string }> = {
  budget: {
    title: "Trade-spend allocation (LKR 5M, Western Province)",
    desc: "Concave water-filling optimisation split across discount, merchandising, and promotional channels.",
  },
  "cooler-roi": {
    title: "Cooler deployment ROI",
    desc: "Per-outlet business case for adding a cooler — NPV, payback, lifetime value.",
  },
  dormancy: {
    title: "Dormancy risk early warning",
    desc: "Outlets most likely to lapse over the next quarter. Sales-rep intervention list.",
  },
  scorecard: {
    title: "Distributor operational scorecard",
    desc: "Eight-dimension benchmark of the ten distributors with a composite health rank.",
  },
  territories: {
    title: "Sales territories",
    desc: "HDBSCAN clusters of outlets that form natural sub-province sales territories.",
  },
  forensics: {
    title: "Data forensics findings",
    desc: "Beyond-DQ artefacts surfaced before modelling.",
  },
};

function isValidView(v: string | string[] | undefined): v is ViewKey {
  if (typeof v !== "string") return false;
  return (VIEW_KEYS as readonly string[]).includes(v);
}

export default async function InsightsPage({
  searchParams,
}: {
  searchParams: Search;
}) {
  const raw = Array.isArray(searchParams.view)
    ? searchParams.view[0]
    : searchParams.view;
  const view: ViewKey = isValidView(raw) ? raw : "budget";
  const meta = TITLES[view];

  return (
    <>
      <PageHeader title={meta.title} description={meta.desc} />
      <InsightTabs active={view} />

      {(() => {
        const rawPage = Array.isArray(searchParams.page)
          ? searchParams.page[0]
          : searchParams.page;
        const page = Math.max(1, Number(rawPage) || 1);
        switch (view) {
          case "budget":
            return <BudgetView />;
          case "cooler-roi":
            return <CoolerRoiView page={page} />;
          case "dormancy":
            return <DormancyView page={page} />;
          case "scorecard":
            return <ScorecardView />;
          case "territories":
            return <TerritoriesView page={page} />;
          case "forensics":
            return <ForensicsView />;
        }
      })()}
    </>
  );
}
