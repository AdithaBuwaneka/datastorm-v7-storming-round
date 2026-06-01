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

# --- POI tags for Overpass (FMCG-beverage industry-relevant) ---
POI_TAGS = [
    # Direct beverage-consumption venues (industry-critical)
    ("amenity", "cafe"),            # coffee/tea shops
    ("amenity", "fast_food"),       # quick eats
    ("amenity", "restaurant"),      # full-service
    ("amenity", "food_court"),      # mall food courts
    ("amenity", "ice_cream"),       # beverage co-consumption

    # Education footfall
    ("amenity", "school"),
    ("amenity", "university"),
    ("amenity", "college"),
    ("amenity", "kindergarten"),

    # Healthcare footfall
    ("amenity", "hospital"),
    ("amenity", "clinic"),
    ("amenity", "pharmacy"),

    # Transit / commerce hubs
    ("highway", "bus_stop"),
    ("amenity", "bus_station"),
    ("amenity", "taxi"),
    ("railway", "station"),
    ("amenity", "marketplace"),
    ("amenity", "market"),
    ("amenity", "fuel"),
    ("amenity", "bank"),

    # Retail competition / co-located
    ("shop",    "supermarket"),
    ("shop",    "convenience"),
    ("shop",    "general"),
    ("shop",    "alcohol"),

    # Community gatherings (event-driven beverage demand)
    ("amenity", "place_of_worship"),
    ("historic", "temple"),
    ("leisure", "park"),
    ("leisure", "fitness_centre"),  # sports/energy drink demand
    ("leisure", "stadium"),         # event peak demand

    # Tourism (urban + tourist-area context)
    ("tourism", "hotel"),
    ("tourism", "guest_house"),
    ("tourism", "attraction"),
    ("tourism", "viewpoint"),
    ("leisure", "beach_resort"),
    ("natural", "beach"),

    # Population proxy
    ("landuse", "residential"),     # catchment population indicator
]

# --- POI category mapping (for distance-decay scores) ---
# Every tag in POI_TAGS must appear in at least one category so the
# distance-decay scoring covers the full POI inventory (no orphan tags).
POI_CATEGORIES = {
    "footfall": [
        ("highway", "bus_stop"),
        ("amenity", "bus_station"),
        ("amenity", "taxi"),
        ("railway", "station"),
        ("amenity", "fuel"),
        ("amenity", "bank"),       # commerce-hub footfall
    ],
    "school": [
        ("amenity", "school"),
        ("amenity", "university"),
        ("amenity", "college"),
        ("amenity", "kindergarten"),
    ],
    "tourist": [
        ("tourism", "hotel"),
        ("tourism", "guest_house"),
        ("tourism", "attraction"),
        ("tourism", "viewpoint"),
        ("leisure", "beach_resort"),
        ("natural", "beach"),
    ],
    "health": [
        ("amenity", "hospital"),
        ("amenity", "clinic"),
        ("amenity", "pharmacy"),
    ],
    "competitor_poi": [
        ("shop", "supermarket"),
        ("shop", "convenience"),
        ("shop", "general"),
        ("amenity", "marketplace"),
        ("amenity", "market"),
        ("shop", "alcohol"),       # direct beverage competitor
    ],
    "worship": [
        ("amenity", "place_of_worship"),
        ("historic", "temple"),
    ],
    "food_service": [
        ("amenity", "restaurant"),
        ("amenity", "cafe"),
        ("amenity", "fast_food"),
        ("amenity", "food_court"),
        ("amenity", "ice_cream"),  # beverage co-consumption
    ],
    "leisure_rec": [
        ("leisure", "park"),
        ("leisure", "fitness_centre"),
        ("leisure", "stadium"),
    ],
    "population": [
        ("landuse", "residential"),  # catchment-population proxy
    ],
}

POI_CATEGORY_OUTPUT = {
    "footfall": "footfall_score",
    "school": "school_score",
    "tourist": "tourist_score",
    "health": "health_score",
    "competitor_poi": "competitor_poi_score",
    "worship": "worship_score",
    "food_service": "food_pairing_score",
    "leisure_rec": "leisure_rec_score",
    "population": "population_score",
}

# Distance-decay configuration (meters)
POI_SEARCH_RADIUS_M = {
    "footfall": 500,
    "school": 1000,
    "tourist": 2000,
    "health": 1000,
    "competitor_poi": 800,
    "worship": 1000,
    "food_service": 300,
    "leisure_rec": 1500,
    "population": 1500,
}

# Gaussian sigma per category (meters)
POI_SIGMA_M = {
    "footfall": 150,
    "school": 400,
    "tourist": 1000,
    "health": 400,
    "worship": 300,
    "food_service": 150,
    "leisure_rec": 500,
    "population": 600,
}

# Decay model per category
POI_DECAY_MODEL = {
    "footfall": "gaussian",
    "school": "gaussian",
    "tourist": "gaussian",
    "health": "gaussian",
    "worship": "gaussian",
    "food_service": "gaussian",
    "competitor_poi": "gravity",
    "leisure_rec": "gaussian",
    "population": "gaussian",
}

# POI search radii (meters) — 4 rings for finer catchment granularity
POI_RADII_M = [500, 1000, 2000, 5000]

# --- Climate (Sri Lanka January monthly averages, by province) ---
# Source: Department of Meteorology Sri Lanka — typical Jan conditions
# (temperature in deg C; humidity in %).
# Beverages are climate-sensitive: hotter / drier = higher soft-drink consumption.
PROVINCE_CLIMATE_JAN = {
    "Western":       {"temp_c": 27.5, "humidity_pct": 75},
    "Central":       {"temp_c": 22.5, "humidity_pct": 78},  # cooler hills
    "Southern":      {"temp_c": 27.0, "humidity_pct": 79},
    "North-Western": {"temp_c": 27.5, "humidity_pct": 72},  # drier zone
}

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
