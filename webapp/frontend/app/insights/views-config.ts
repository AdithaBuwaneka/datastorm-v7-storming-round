export type ViewKey =
  | "budget"
  | "cooler-roi"
  | "dormancy"
  | "scorecard"
  | "territories"
  | "forensics";

export const VIEW_KEYS: readonly ViewKey[] = [
  "budget",
  "cooler-roi",
  "dormancy",
  "scorecard",
  "territories",
  "forensics",
] as const;

export const VIEW_LABELS: Record<ViewKey, string> = {
  budget: "Budget (LKR 5M)",
  "cooler-roi": "Cooler ROI",
  dormancy: "Dormancy risk",
  scorecard: "Distributor scorecard",
  territories: "Territories",
  forensics: "Forensics",
};
