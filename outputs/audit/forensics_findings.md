# Forensics Findings — Legacy SFA Artifacts

These findings go beyond generic DQ rules. They identify system-artifacts
characteristic of legacy Sales Force Automation and distributor ERP exports:
automated ghost entries, human shortcuts, connectivity blackouts, and
master-data decay. Treatments distinguish cleaned (silently corrected),
quarantined (removed from clean dataset), and flagged (kept but tagged for
downstream modeling).

| Finding | Count | Treatment | Examples | Detail |
|---|---|---|---|---|
| Stockout months (zero sandwiched between non-zero) | 82,810 | flagged_for_modeling |  | Used as constraint indicator in Phase 5 (not quarantined). |
| Dead-then-resurrected outlets | 2,783 | flagged | OUT_00406; OUT_00408; OUT_00420; OUT_00430; OUT_00436 | >= 6 consecutive zero months then resumed — flagged for review. |