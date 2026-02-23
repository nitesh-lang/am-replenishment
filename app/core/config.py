import os
from dotenv import load_dotenv

# -------------------------------------------------
# LOAD ENVIRONMENT VARIABLES
# -------------------------------------------------
load_dotenv()

# -------------------------------------------------
# ENVIRONMENT
# -------------------------------------------------
ENV = os.getenv("ENV", "local")  # local / staging / prod

# -------------------------------------------------
# DATABASE CONFIG (PostgreSQL)
# -------------------------------------------------
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "database": os.getenv("DB_NAME", "am_replenishment"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", "postgres"),
}

# SQLAlchemy connection string
DATABASE_URL = (
    f"postgresql+psycopg2://{DB_CONFIG['user']}:{DB_CONFIG['password']}"
    f"@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}"
)

# -------------------------------------------------
# BUSINESS CONSTANTS (SAFE TO TUNE)
# -------------------------------------------------

# Default planning horizon
DEFAULT_TARGET_WEEKS = 2

# Sales averaging window
SALES_LOOKBACK_WEEKS = 8  # 2 months

# B2B stock handling
B2B_MAX_AGE_DAYS = 90          # beyond this, ignored
B2B_WEIGHT_FACTOR = 0.6        # only 60% trusted

# Master carton rounding
ROUND_TO_MASTER_CARTON = True

# Replenishment safety caps
MAX_REPLENISHMENT_MULTIPLIER = 2.5  # vs avg weekly sales

# -------------------------------------------------
# AMAZON FC MASTER LIST (LOCKED)
# -------------------------------------------------
AMAZON_FCS = [
    "DEL4", "HYD8", "BLR7", "DEL5", "AMD2", "BLR8",
    "BOM5", "CCX1", "CJB1", "DED4", "HYD3", "MAA4",
    "PNQ3", "BOM7", "ISK3", "LKO1", "CCX4"
]

# -------------------------------------------------
# INVENTORY DISPOSITIONS (STRICT)
# -------------------------------------------------
SELLABLE_DISPOSITIONS = ["SELLABLE"]

NON_SELLABLE_DISPOSITIONS = [
    "CARRIER_DAMAGED",
    "CUSTOMER_DAMAGED",
    "DEFECTIVE",
    "WAREHOUSE_DAMAGED",
    "LOST"
]

# -------------------------------------------------
# RUN STATUS FLAGS
# -------------------------------------------------
RUN_STATUS = {
    "DRAFT": "draft",
    "LOCKED": "locked",
    "BLOCKED": "blocked"
}

# -------------------------------------------------
# VALIDATION THRESHOLDS
# -------------------------------------------------
VALIDATION_LIMITS = {
    "max_negative_stock": 0,
    "max_fc_allocation_pct": 0.7,
    "max_b2b_pct": 0.3,
}

# -------------------------------------------------
# LOGGING
# -------------------------------------------------
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_DIR = os.getenv("LOG_DIR", "logs")

# -------------------------------------------------
# FILE STORAGE (RAW UPLOADS)
# -------------------------------------------------
RAW_DATA_DIR = os.getenv("RAW_DATA_DIR", "data/raw")
PROCESSED_DATA_DIR = os.getenv("PROCESSED_DATA_DIR", "data/processed")
