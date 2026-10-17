"""Load + clean the opportunities file (and optional applications file)."""
import html
import re
from pathlib import Path

import pandas as pd

import config as cfg

NULL_STRINGS = {"", "nan", "none", "null", "n/a", "na", "<na>"}
TRUE_SET = {"true", "1", "1.0", "yes", "y", "t"}
FALSE_SET = {"false", "0", "0.0", "no", "n", "f"}
# microscholarship in values ka matlab "scholarship nahi hai"
NO_SCHOLARSHIP = {"", "0", "0.0", "false", "no", "none", "nan", "null", "[]", "{}"}
HTML_COLS = ["long_description", "short_description", "summary", "role_responsibility",
             "Eligibility", "Reward", "Testimonial"]


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------
def _read(path, sheet):
    path = Path(path)
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path)
    return pd.read_excel(path, sheet_name=sheet)


def _is_app_file(p):
    return any(k in p.name.lower() for k in ("application", "signup", "sign_up", "sign-up"))


def find_files():
    files = [p for p in sorted(cfg.DATA_DIR.glob("*"))
             if p.suffix.lower() in (".xlsx", ".xls", ".csv") and not p.name.startswith("~$")]
    opp = cfg.DATA_DIR / cfg.OPP_FILE if cfg.OPP_FILE else next((p for p in files if not _is_app_file(p)), None)
    app = cfg.DATA_DIR / cfg.APP_FILE if cfg.APP_FILE else next((p for p in files if _is_app_file(p)), None)
    if opp is None or not Path(opp).exists():
        raise FileNotFoundError(f"Opportunities file nahi mili. Isay yahan rakho: {cfg.DATA_DIR}")
    return opp, app


def _norm(name):
    return re.sub(r"[\s_]+", "", str(name)).lower()


def _resolve(df, name):
    """Config ke column name ko file ke asli column se match karo (case/space ignore)."""
    if not name:
        return None
    for c in df.columns:
        if _norm(c) == _norm(name):
            return c
    return None


def _clean_text(df):
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    for c in df.select_dtypes(include=["object", "string"]).columns:
        s = df[c].astype("string").str.strip().str.replace(r"\s+", " ", regex=True)
        df[c] = s.mask(s.str.lower().isin(NULL_STRINGS).fillna(False))
    return df


def _strip_html(x):
    if pd.isna(x):
        return x
    x = re.sub(r"<[^>]+>", " ", str(x))
    return re.sub(r"\s+", " ", html.unescape(x)).strip()


def _to_bool(s):
    def f(x):
        if pd.isna(x):
            return pd.NA
        t = str(x).strip().lower()
        return True if t in TRUE_SET else False if t in FALSE_SET else pd.NA
    return s.map(f).astype("boolean")


def _norm_id(s):
    return s.astype("string").str.strip().str.replace(r"\.0$", "", regex=True)


def _parse_number(s):
    """Text mein se pehla number nikalo ('Rs. 5,000' -> 5000)."""
    t = s.astype("string").str.replace(",", "", regex=False).str.extract(r"(-?\d+(?:\.\d+)?)")[0]
    return pd.to_numeric(t, errors="coerce")


def _has_scholarship(s):
    t = s.astype("string").str.strip().str.lower()
    return (s.notna() & ~t.isin(NO_SCHOLARSHIP).fillna(False)).astype(bool)


def _na_series(df, dtype="string"):
    return pd.Series(pd.NA, index=df.index, dtype=dtype)


def _to_date(s):
    return pd.to_datetime(s, errors="coerce", utc=True).dt.tz_localize(None).dt.normalize()


# ----------------------------------------------------------------------
# opportunities
# ----------------------------------------------------------------------
def load_opportunities(log):
    path, _ = find_files()
    raw = _read(path, cfg.OPP_SHEET)
    log.append(f"Opportunities file: {Path(path).name} ({raw.shape[0]:,} rows x {raw.shape[1]} columns)")
    df = _clean_text(raw)

    # HTML tags hatao
    for name in HTML_COLS:
        c = _resolve(df, name)
        if c and df[c].astype("string").str.contains("<", na=False).any():
            df[c] = df[c].map(_strip_html)
            log.append(f"HTML tags removed from: {c}")

    # dates
    created = _resolve(df, cfg.OPP_COLS["created"])
    for name in {cfg.OPP_COLS["created"], "modified_at", "last_date_to_apply"}:
        c = _resolve(df, name)
        if c:
            df[c] = _to_date(df[c])

    # duplicates
    n0 = len(df)
    df = df.drop_duplicates()
    log.append(f"Exact duplicate rows removed: {n0 - len(df):,}")

    idc = _resolve(df, cfg.OPP_COLS["id"])
    if not idc:
        raise ValueError(f"Opportunity id column '{cfg.OPP_COLS['id']}' nahi mila. Columns: {list(df.columns)}")
    out = df.copy()
    out["opp_id"] = _norm_id(df[idc])
    modc = _resolve(df, "modified_at")
    n0 = len(out)
    if modc:
        out = out.sort_values(modc, kind="stable")
    out = out.drop_duplicates("opp_id", keep="last").sort_index()
    log.append(f"Duplicate opportunity_id removed (latest modified_at kept): {n0 - len(out):,}")

    def col(key):
        c = _resolve(out, cfg.OPP_COLS.get(key))
        if cfg.OPP_COLS.get(key) and not c:
            log.append(f"WARNING: mapped column '{cfg.OPP_COLS[key]}' ({key}) not found in opportunities file")
        return out[c] if c else _na_series(out)

    out["opp_name"] = col("name")
    out["opp_category"] = col("category").fillna("Uncategorized")
    out["opp_created"] = out[created] if created else _na_series(out, "datetime64[ns]")
    out["opp_archived"] = _to_bool(col("archived"))
    out["reward_raw"] = col("reward").astype("string")
    out["reward_num"] = _parse_number(out["reward_raw"])
    out["scholarship_raw"] = col("scholarship").astype("string")
    out["has_scholarship"] = _has_scholarship(out["scholarship_raw"])
    out["opp_lead_source"] = col("lead_source").fillna("Unknown")
    log.append(f"Opportunities after cleaning: {len(out):,}")
    return out.reset_index(drop=True)


# ----------------------------------------------------------------------
# applications (optional)
# ----------------------------------------------------------------------
def load_applications(opps, log):
    _, path = find_files()
    if path is None:
        log.append("Applications file: not found -> sign-up / completion / lead-source metrics are OFF")
        return None
    raw = _read(path, cfg.APP_SHEET)
    log.append(f"Applications file: {Path(path).name} ({raw.shape[0]:,} rows x {raw.shape[1]} columns)")
    df = _clean_text(raw)

    oc = _resolve(df, cfg.APP_COLS["opportunity_id"])
    dc = _resolve(df, cfg.APP_COLS["date"])
    if not oc or not dc:
        raise ValueError("Applications file mein opportunity_id / date column nahi mile. "
                         f"config.py ka APP_COLS theek karo. File ke columns: {list(df.columns)}")

    out = pd.DataFrame(index=df.index)
    out["app_opp_id"] = _norm_id(df[oc])
    out["app_date"] = _to_date(df[dc])
    idc = _resolve(df, cfg.APP_COLS["id"])
    out["app_id"] = _norm_id(df[idc]) if idc else pd.Series(range(len(df)), index=df.index).astype("string")

    sc = _resolve(df, cfg.APP_COLS["lead_source"])
    out["app_lead_source"] = (df[sc] if sc else _na_series(df)).fillna("Unknown")

    cc = _resolve(df, cfg.APP_COLS["completed"])
    stc = _resolve(df, cfg.APP_COLS["status"])
    out["app_status"] = df[stc] if stc else _na_series(df)
    if cc:
        out["app_completed"] = _to_bool(df[cc]).fillna(False).astype(bool)
    elif stc:
        out["app_completed"] = df[stc].astype("string").str.lower().isin(cfg.COMPLETED_VALUES).fillna(False).astype(bool)
    else:
        out["app_completed"] = False
        log.append("WARNING: no status/completed column in applications -> completion rate OFF")

    if idc:
        n0 = len(out)
        out = out.drop_duplicates("app_id")
        log.append(f"Duplicate applications (same id) removed: {n0 - len(out):,}")
    else:
        log.append("No application id column -> duplicate applications NOT removed "
                   "(set APP_COLS['id'] if you have one)")

    orphan = ~out.app_opp_id.isin(opps.opp_id)
    if orphan.any():
        log.append(f"Applications whose opportunity_id is not in opportunities (dropped): {int(orphan.sum()):,}")
        out = out[~orphan]
    miss = int(out.app_date.isna().sum())
    if miss:
        log.append(f"Applications with missing/invalid date (kept in totals, excluded from trends): {miss:,}")
    log.append(f"Applications after cleaning: {len(out):,}")
    return out.reset_index(drop=True)


# ----------------------------------------------------------------------
def quality_report(df):
    cols = [c for c in df.columns]
    return pd.DataFrame({
        "column": cols,
        "dtype": [str(df[c].dtype) for c in cols],
        "missing": [int(df[c].isna().sum()) for c in cols],
        "missing_pct": [round(float(df[c].isna().mean() * 100), 2) for c in cols],
        "unique": [int(df[c].nunique()) for c in cols],
    }).sort_values("missing_pct", ascending=False)


def load_all():
    log = []
    opps = load_opportunities(log)
    apps = load_applications(opps, log)
    return {"opps": opps, "apps": apps, "log": log}

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