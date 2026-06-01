"""Prescriptive action cards per outlet.

Combines three signal sources into ranked recommendations:

  1. Counterfactual deltas — "what if we removed a known constraint?"
       cf_add_cooler, cf_zero_competition (computed by xai_attribution)
  2. SKU mix gap — outlet's current premium share vs peer-cohort high performers
       suggests a stock-and-price intervention
  3. Festival/seasonality — Sri Lanka calendar months with biggest expected lift
       suggests a timed promotional intervention

For each outlet we emit up to 4 candidate actions, scored by expected monthly
liter uplift, and persist the top-3 to disk for the web UI / LLM narrative.

Outputs:
    data/gold/outlet_actions.parquet         - one row per (Outlet_ID, rank)
    outputs/audit/outlet_actions_top3.csv    - first 3 rows per outlet, flat
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src import config


# Sri Lanka festival / seasonal beverage-demand months (rough lift multipliers).
# These are heuristic uplift fractions over an outlet's own Jan-baseline.
SL_FESTIVAL_LIFT = {
    4:  ("Sinhala-Tamil New Year (Avurudu)", 0.18),
    5:  ("Vesak Poya",                       0.10),
    7:  ("Esala Poya / school holidays",     0.12),
    11: ("Year-end retail surge",            0.10),
    12: ("Christmas + New Year peak",        0.20),
}

# Peer premium-share benchmark: top quartile of high-performing peers
PREMIUM_TOP_QUANTILE = 0.75
PREMIUM_LIFT_FRACTION = 0.06   # 6% volume uplift for shifting toward premium mix


def _peer_premium_benchmark(feats: pd.DataFrame) -> pd.DataFrame:
    """Per (Outlet_Type, Outlet_Size, Province) cohort, find the
    top-quartile premium_share among above-average performers."""
    cohort_cols = ["Outlet_Type", "Outlet_Size", "Province"]
    above_avg = feats[feats["monthly_volume_mean"] >=
                       feats["monthly_volume_mean"].median()]
    bench = (above_avg
             .groupby(cohort_cols)["premium_share"]
             .quantile(PREMIUM_TOP_QUANTILE)
             .reset_index()
             .rename(columns={"premium_share": "peer_premium_top_share"}))
    return bench


def build_action_cards(feats: pd.DataFrame,
                       counterfactuals: pd.DataFrame) -> pd.DataFrame:
    """Return a long-form DataFrame: Outlet_ID, rank, action, uplift_L,
    rationale, action_type."""
    df = feats.merge(counterfactuals, on="Outlet_ID", how="inner")
    bench = _peer_premium_benchmark(feats)
    df = df.merge(bench, on=["Outlet_Type", "Outlet_Size", "Province"], how="left")

    base = df["base_pred"].fillna(0.0).clip(lower=0.0)

    cards: list[dict] = []
    for _, row in df.iterrows():
        oid = row["Outlet_ID"]
        b = float(base.loc[row.name])
        candidates = []

        # Candidate 1: Add a cooler
        cooler_uplift = float(row.get("delta_add_cooler", 0.0) or 0.0)
        if cooler_uplift > 0:
            current_count = int(row.get("Cooler_Count", 0) or 0)
            verb = "Place first cooler at outlet" if current_count == 0 else \
                   f"Add {current_count + 1}th cooler to outlet"
            candidates.append({
                "action_type": "cooler",
                "action": verb,
                "uplift_L": cooler_uplift,
                "rationale": (f"Counterfactual model predicts +{cooler_uplift:.1f} L/month "
                              f"if cooler capacity is increased."),
            })

        # Candidate 2: Reduce nearby competitor pressure (proxy: prime-location merchandising)
        comp_uplift = float(row.get("delta_zero_competition", 0.0) or 0.0)
        comp_pressure = float(row.get("type_weighted_pressure", 0.0) or 0.0)
        if comp_uplift > 1 and comp_pressure > 5:
            candidates.append({
                "action_type": "merchandising",
                "action": "Deploy prime-shelf branded merchandising (posters, shelf-talkers)",
                "uplift_L": comp_uplift * 0.4,   # haircut: merch can't reach full no-competition uplift
                "rationale": (f"Outlet faces type-weighted competition pressure of "
                              f"{comp_pressure:.1f} from nearby same-type stores. Targeted "
                              f"in-store branded visibility recovers an estimated "
                              f"{comp_uplift * 0.4:.1f} L/month of intercepted traffic."),
            })

        # Candidate 3: Shift SKU mix toward premium (closing the peer gap)
        prem = float(row.get("premium_share", 0.0) or 0.0)
        prem_bench = float(row.get("peer_premium_top_share", prem) or prem)
        prem_gap = max(0.0, prem_bench - prem)
        if prem_gap > 0.05:
            mix_uplift = b * PREMIUM_LIFT_FRACTION * (prem_gap / 0.10)
            candidates.append({
                "action_type": "sku_mix",
                "action": ("Shift SKU mix toward premium (stock 1-2 additional "
                            "premium SKUs)"),
                "uplift_L": mix_uplift,
                "rationale": (f"Outlet currently sells {prem*100:.1f}% premium SKUs vs "
                              f"top-performing peers in the same cohort at {prem_bench*100:.1f}%. "
                              f"Closing this gap typically lifts volume by "
                              f"~{mix_uplift:.1f} L/month."),
            })

        # Candidate 4: Best festival month to push promotions
        best_month_lift = 0.0
        best_month_name = ""
        for m, (name, lift) in SL_FESTIVAL_LIFT.items():
            candidate_lift = b * lift
            if candidate_lift > best_month_lift:
                best_month_lift = candidate_lift
                best_month_name = name
        if best_month_lift > 1:
            candidates.append({
                "action_type": "festival_promo",
                "action": f"Schedule promotional push for {best_month_name}",
                "uplift_L": best_month_lift,
                "rationale": (f"Historical seasonality and Sri Lanka demand calendar imply "
                              f"~{best_month_lift:.1f} L/month additional volume during "
                              f"{best_month_name} if outlet is featured in the campaign."),
            })

        # Rank candidates by predicted uplift
        candidates.sort(key=lambda x: x["uplift_L"], reverse=True)
        for rank, c in enumerate(candidates[:3], 1):
            cards.append({
                "Outlet_ID": oid,
                "rank": rank,
                "action_type": c["action_type"],
                "action": c["action"],
                "predicted_uplift_L_per_month": round(c["uplift_L"], 2),
                "rationale": c["rationale"],
            })

    return pd.DataFrame(cards)


def write_outputs(cards: pd.DataFrame) -> None:
    config.AUDIT.mkdir(parents=True, exist_ok=True)
    config.GOLD.mkdir(parents=True, exist_ok=True)

    parq_path = config.GOLD / "outlet_actions.parquet"
    cards.to_parquet(parq_path, index=False)
    print(f"  -> {parq_path}  shape={cards.shape}")

    # Flat CSV of all top-3 actions per outlet
    csv_path = config.AUDIT / "outlet_actions_top3.csv"
    cards.to_csv(csv_path, index=False)
    print(f"  -> {csv_path}")

    # Action-type distribution audit
    if "action_type" in cards.columns and not cards.empty:
        by_type = (cards.groupby(["rank", "action_type"]).size()
                   .reset_index(name="n")
                   .pivot(index="action_type", columns="rank", values="n")
                   .fillna(0).astype(int))
        type_path = config.AUDIT / "outlet_actions_rank_distribution.csv"
        by_type.to_csv(type_path)
        print(f"  -> {type_path}")
        print(by_type.to_string())


def main() -> None:
    print("\n" + "=" * 70)
    print("Prescriptive outlet action cards")
    print("=" * 70)

    feats = pd.read_parquet(config.GOLD / "outlet_features.parquet")
    cf = pd.read_parquet(config.GOLD / "counterfactuals.parquet")

    cards = build_action_cards(feats, cf)
    n_outlets_with_actions = cards["Outlet_ID"].nunique() if not cards.empty else 0
    print(f"  Outlets with at least 1 action: {n_outlets_with_actions:,}")
    print(f"  Total action cards generated:   {len(cards):,}")
    if not cards.empty:
        print(f"  Median predicted uplift (top-1 action): "
              f"{cards[cards['rank']==1]['predicted_uplift_L_per_month'].median():.1f} L/mo")
        print(f"  Sum predicted uplift across all rank-1 actions: "
              f"{cards[cards['rank']==1]['predicted_uplift_L_per_month'].sum():,.0f} L/mo")

    write_outputs(cards)
    print("\nOutlet action cards: OK")


if __name__ == "__main__":
    main()
