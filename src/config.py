"""Single source of truth for paths, constants, and competition-specific values."""
import os
from pathlib import Path

# --- Paths ---
PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Raw competition data is NOT committed to the repo (large + competition-owned).
# Default location: <repo>/data/source/  — place the 6 raw files here.
# Override path with env var DATASTORM_RAW_DIR if your files live elsewhere.
DEFAULT_SOURCE = PROJECT_ROOT / "data" / "source"
RAW_SOURCE = Path(os.environ.get("DATASTORM_RAW_DIR", str(DEFAULT_SOURCE)))

DATA          = PROJECT_ROOT / "data"
BRONZE        = DATA / "bronze"
POI_RAW       = BRONZE / "poi_raw"
SILVER_CLEAN  = DATA / "silver" / "clean"
QUARANTINE    = DATA / "silver" / "quarantine"
GOLD          = DATA / "gold"

OUTPUTS       = PROJECT_ROOT / "outputs"
AUDIT         = OUTPUTS / "audit"
REPORT        = PROJECT_ROOT / "report"
FIGURES       = REPORT / "figures"
DOCS          = PROJECT_ROOT / "docs"

# --- Competition constants ---
TEAM_NAME = "DataX"
TARGET_YEAR  = 2026
TARGET_MONTH = 1

# --- Domain constants ---
VALID_DISTRIBUTOR_IDS = {
    "DIST_W_01", "DIST_W_02", "DIST_W_03",
    "DIST_C_01", "DIST_C_02", "DIST_C_03",
    "DIST_NW_01", "DIST_NW_02",
    "DIST_S_01", "DIST_S_02",
}

# Sri Lanka geographic bounds
SL_LAT_BOUNDS = (5.9, 9.9)
SL_LON_BOUNDS = (79.5, 82.0)
SL_BBOX = (5.9, 79.5, 9.9, 82.0)   # (south, west, north, east) for Overpass

# Province extraction from Distributor_ID prefix
DISTRIBUTOR_TO_PROVINCE = {
    "DIST_W_01": "Western",  "DIST_W_02": "Western",  "DIST_W_03": "Western",
    "DIST_C_01": "Central",  "DIST_C_02": "Central",  "DIST_C_03": "Central",
    "DIST_NW_01": "North-Western", "DIST_NW_02": "North-Western",
    "DIST_S_01": "Southern", "DIST_S_02": "Southern",
}

# Seasonality categorical values (case-sensitive set as appears in raw file)
VALID_SEASONALITY = {"Favorable", "Moderate", "Un-Favorable"}

# Holiday types
VALID_HOLIDAY_TYPES = {"Public", "Bank", "Poya Day", "Mercantile"}

# Outlet sizes (per codebook)
VALID_OUTLET_SIZES = {"Small", "Medium", "Large", "Extra Large"}

# --- POI tags for Overpass (15 tags, FMCG-beverage relevant) ---
POI_TAGS = [
    ("amenity", "school"),
    ("amenity", "university"),
    ("amenity", "hospital"),
    ("amenity", "pharmacy"),
    ("amenity", "restaurant"),
    ("amenity", "marketplace"),
    ("amenity", "place_of_worship"),
    ("amenity", "bank"),
    ("amenity", "fuel"),
    ("highway", "bus_stop"),
    ("shop",    "supermarket"),
    ("shop",    "convenience"),
    ("shop",    "alcohol"),
    ("tourism", "hotel"),
    ("tourism", "attraction"),
    ("leisure", "park"),
]

# POI search radii (meters)
POI_RADII_M = [1000, 2000, 5000]

# --- Modeling constants ---
PEER_GROUP_MIN_N = 30          # minimum n for Q90 estimation; below this trigger fallback
PEER_QUANTILE = 0.90            # primary ceiling quantile
SANITY_FLOOR_QUANTILE = 0.95    # use Q95 of own history as floor (robust vs max)
SANITY_CEILING_MULT = 5.0       # final <= 5 x peer_cohort_q99
YOY_CLIP = (0.85, 1.30)         # clip year-over-year growth multiplier
CONSTRAINED_SHARE_THRESHOLD = 0.25  # outlet considered "suppressed" if > 25% months constrained
TOBIT_BLEND_W_PEER = 0.6        # weight of peer-Q90 in final blend
TOBIT_BLEND_W_TOBIT = 0.4       # weight of tobit prediction in final blend
TOBIT_CONVERGENCE_RHO = 0.75    # Spearman threshold for considering methods convergent

# --- Output ---
PREDICTIONS_CSV = OUTPUTS / f"{TEAM_NAME}_predictions.csv"
PDF_REPORT      = REPORT / f"{TEAM_NAME}_report.pdf"
