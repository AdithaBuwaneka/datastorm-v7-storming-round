export interface Summary {
  n_outlets: number;
  total_predicted_jan2026_L: number;
  median_predicted_jan2026_L: number;
  budget_allocated_LKR: number;
  outlets_high_or_critical_risk: number;
  cooler_top100_capex_LKR: number;
  cooler_top100_24mo_margin_LKR: number;
  outlets_by_province: Record<string, number>;
}

export interface OutletRow {
  Outlet_ID: string;
  Outlet_Type: string;
  Outlet_Size: string;
  Distributor_ID: string;
  Province: string;
  Cooler_Count: number;
  Latitude: number;
  Longitude: number;
  active_months: number;
  monthly_volume_mean: number;
  monthly_volume_q90: number;
  competitors_1km: number;
  hhi_1500m: number;
  spatial_demand_score: number;
  replenishment_friction: number;
  Maximum_Monthly_Liters: number;
  dormancy_risk_score: number | null;
  risk_band: "low" | "moderate" | "high" | "critical" | null;
  cluster_id: number | null;
  Trade_Spend_LKR: number | null;
}

export interface ShapDriver {
  direction: "positive" | "negative";
  feature: string;
  shap: number;
}

export interface ActionCard {
  Outlet_ID: string;
  rank: number;
  action_type: string;
  action: string;
  predicted_uplift_L_per_month: number;
  rationale: string;
}

export interface OutletDetail {
  outlet: OutletRow;
  top_drivers: ShapDriver[];
  counterfactual: {
    base_pred?: number;
    cf_add_cooler?: number;
    cf_zero_competition?: number;
    delta_add_cooler?: number;
    delta_zero_competition?: number;
  };
  recommended_actions: ActionCard[];
  cooler_roi: Record<string, any>;
}

export type RiskBand = "low" | "moderate" | "high" | "critical";
