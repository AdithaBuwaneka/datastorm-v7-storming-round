# Forensics Findings — Legacy SFA Artifacts

These findings go beyond generic DQ rules. They identify system-artifacts
characteristic of legacy Sales Force Automation and distributor ERP exports:
automated ghost entries, human shortcuts, connectivity blackouts, and
master-data decay. Treatments distinguish cleaned (silently corrected),
quarantined (removed from clean dataset), and flagged (kept but tagged for
downstream modeling).

| Finding | Count | Treatment | Examples | Detail |
|---|---|---|---|---|
| Cross-file Outlet_ID integrity | 0 | reported_clean | perfect alignment master == coords == transactions (n=20000) | Unusual for legacy SFA exports; suggests upstream curation. Row-level anomalies remain primary forensic focus. |
| Outlet_Type typos normalised | 585 | cleaned | 'Grocry'->'Grocery' (n=389); ' Eatery '->'Eatery' (n=196) | 2 distinct typo->canonical mappings applied |
| Transaction value classification | 0 | cleaned_and_flagged | normal_sale=2,299,124; return=4,611 | 3-way classification: data_error+null_row quarantined; return/promo_or_error/foc_promo flagged and kept (signal, not noise). |
| Codebook references absent column | 1 | flagged | 'Product_Name' missing from transactions_history_final.csv | Codebook documents this field but raw export omits it; treated as documentation drift, not data quality issue. |
| Codebook filename divergence | 1 | flagged | distributor_seasonality.csv claimed vs distributor_seasonality_details.csv actual | No impact on data; logged as governance finding. |
| Automated-entry signatures | 0 | none_found |  | No (Outlet, SKU) pair with >= 6 consecutive identical Volume_Liters. |
| Stockout months (zero sandwiched between non-zero) | 81,165 | flagged_for_modeling |  | Used as constraint indicator in Phase 5 (not quarantined). |
| Dead-then-resurrected outlets | 2,704 | flagged | OUT_00406; OUT_00408; OUT_00420; OUT_00430; OUT_00436 | >= 6 consecutive zero months then resumed — flagged for review. |