# Raw Data Placement

Place the six raw competition files here before running the pipeline:

```
data/source/
├── transactions_history_final.csv
├── outlet_master.csv
├── outlet_coordinates.csv
├── distributor_seasonality_details.csv
├── holiday_list.csv
└── 1. dataset_description.xlsx
```

These files are **not committed to git** (see `.gitignore`).

## How to obtain

Download from the official DataStorm 7.0 Kaggle dataset page provided by the
organizers.

## Override location

If your raw data lives elsewhere on disk, set:

```bash
# Windows PowerShell
$env:DATASTORM_RAW_DIR = "C:\path\to\raw\data"

# bash / Linux / macOS
export DATASTORM_RAW_DIR=/path/to/raw/data
```

The pipeline (`src/bronze_ingest.py`) will read from `$DATASTORM_RAW_DIR`
instead of `data/source/`.
