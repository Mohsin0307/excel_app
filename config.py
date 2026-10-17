"""
Sirf yahi file edit karni hai. Baqi code is config ko parh kar chalta hai.

Folder:
    opportunity_dashboard/
        data/opportunities.xlsx      <- aap ki 33-column file
        data/applications.xlsx       <- (optional) har sign-up/application ki ek row
"""
from pathlib import Path

BASE = Path(__file__).resolve().parent
DATA_DIR = BASE / "data"
OUT_DIR = BASE / "output"

# ---- Files ----------------------------------------------------------
# None = auto-detect. Auto-detect: data/ mein jis file ke naam mein "application" ya
# "signup" ho wo applications file hai, pehli baqi file opportunities file hai.
OPP_FILE = None          # e.g. "opportunities.xlsx"
OPP_SHEET = 0            # sheet ka naam ya number
APP_FILE = None          # e.g. "applications.xlsx"  (ya wohi file, alag sheet ke saath)
APP_SHEET = 0

# ---- Opportunities file: column mapping -----------------------------
# Value = aap ki file ka column name (capital/space ka farq chalta hai). Nahi hai to None.
OPP_COLS = {
    "id": "opportunity_id",
    "name": "name",
    "category": "category",
    "created": "created_at",
    "archived": "is_archived",
    "reward": "Reward",
    "scholarship": "microscholarship",
    "lead_source": None,     # agar opportunities file mein lead source column ho
}

# ---- Applications file: column mapping ------------------------------
# Value list ho to pehla non-empty column use hota hai (coalesce).
APP_COLS = {
    # "auto" = code khud dhoondta hai ke applications ka kaun sa column opportunities se match karta hai
    # (relation_id / work_item_sk / sk / pk ...). Pata ho to column ka naam likh do.
    "opportunity_id": "auto",
    "date": ["apply_date", "created_at"],         # sign-up ki date
    "id": "application_id",                       # unique application id (duplicates hatane ke liye)
    "modified": "modified_at",                    # duplicate id mile to sab se naya record rakhta hai
    "status": "status",
    "completion_date": "completion_date",         # ye bhari ho to application "completed" maani jati hai
    "completed": None,                            # ya True/False column jo completion batata ho
    "lead_source": ["from_where_did_you_hear_about_us",
                    "how_did_you_hear_about_this_opportunity",
                    "from_which_medium_did_you_hear_about_the_internship"],
}
COMPLETED_VALUES = ["completed", "complete", "finished", "graduated", "passed"]  # sirf tab jab completion_date na ho
# "auto" join ke liye opportunities side ke columns jin se match try hoga
OPP_JOIN_COLS = ["opp_id", "pk"]

# ---- Dashboard settings ---------------------------------------------
MIN_SIGNUPS_FOR_RATE = 10    # is se kam sign-ups wali opportunity ka completion rate rank mein nahi
TOP_N = 10
COMPARE_FROM = "2025Q4"
COMPARE_TO = "2026Q1"