"""Load + clean the opportunities file (and optional applications file)."""
import html
import re
from pathlib import Path

import pandas as pd

from . import config as cfg

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


APP_MARKERS = ("application", "signup", "sign_up", "sign-up", "learner")


def _is_app_file(p):
    return any(k in p.name.lower() for k in APP_MARKERS)


def _file_seems_app(p):
    """Naam se na pehchana ho to file ke columns dekh kar decide karo."""
    try:
        df = _read(p, 0)
    except Exception:
        return False
    cols = {_norm(c) for c in df.columns}
    return bool(cols & {"applydate", "applicationid", "relationid", "workitemsk", "completiondate"})


def find_files():
    files = [p for p in sorted(cfg.DATA_DIR.glob("*"))
             if p.suffix.lower() in (".xlsx", ".xls", ".csv") and not p.name.startswith("~$")]
    opp = cfg.DATA_DIR / cfg.OPP_FILE if cfg.OPP_FILE else next((p for p in files if not _is_app_file(p)), None)
    app = cfg.DATA_DIR / cfg.APP_FILE if cfg.APP_FILE else next((p for p in files if _is_app_file(p)), None)
    if app is None:
        app = next((p for p in files if p != opp and _file_seems_app(p)), None)
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
def load_opportunities(log, raw=None, label="uploaded table"):
    if raw is None:
        path, _ = find_files()
        raw = _read(path, cfg.OPP_SHEET)
        label = Path(path).name
    log.append(f"Opportunities: {label} ({raw.shape[0]:,} rows x {raw.shape[1]} columns)")
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
def _resolve_many(df, names):
    if not names:
        return []
    names = [names] if isinstance(names, str) else names
    return [c for c in (_resolve(df, n) for n in names) if c]


def _first_date(df, names):
    cols = _resolve_many(df, names)
    if not cols:
        return None
    s = _to_date(df[cols[0]])
    for c in cols[1:]:
        s = s.fillna(_to_date(df[c]))
    return s


def _first_text(df, names):
    cols = _resolve_many(df, names)
    if not cols:
        return None
    s = df[cols[0]].astype("string")
    for c in cols[1:]:
        s = s.fillna(df[c].astype("string"))
    return s


def _variants(s):
    s = _norm_id(s)
    return {"raw": s, "text after # : /": s.str.split(r"[#:/]", regex=True).str[-1]}


def join_diagnostics(df, opps, forced=None):
    """Applications ka kaun sa column opportunities ke id/pk se kitna match karta hai."""
    opp_sets = {}
    for name in cfg.OPP_JOIN_COLS:
        c = _resolve(opps, name)
        if c:
            for vn, v in _variants(opps[c]).items():
                opp_sets[(name, vn)] = set(v.dropna())
    cands = [_resolve(df, forced)] if forced and forced != "auto" else list(df.columns)
    hint = ("opportunity", "opp", "relation", "work_item", "item")
    rows = []
    for c in cands:
        if c is None or str(df[c].dtype).startswith("datetime"):
            continue
        for avn, av in _variants(df[c]).items():
            av = av.dropna()
            if av.empty or av.str.len().median() > 60:
                continue
            for (oname, ovn), oset in opp_sets.items():
                rows.append({"app_col": c, "app_variant": avn, "opp_col": oname, "opp_variant": ovn,
                             "match_pct": round(float(av.isin(oset).mean() * 100), 1),
                             "_hint": int(any(h in c.lower() for h in hint))})
    d = pd.DataFrame(rows, columns=["app_col", "app_variant", "opp_col", "opp_variant", "match_pct", "_hint"])
    return d.sort_values(["match_pct", "_hint"], ascending=False, ignore_index=True).drop(columns="_hint")


def _match_opportunities(df, opps, forced, log):
    diag = join_diagnostics(df, opps, forced)
    if diag.empty or diag.iloc[0].match_pct < 20:
        raise ValueError("Applications ko opportunities se jorne wala column nahi mila. "
                         "Best candidates:\n" + diag.head(5).to_string(index=False) +
                         "\nconfig.py mein APP_COLS['opportunity_id'] ka sahi column likho.")
    best = diag.iloc[0]
    ok = _variants(opps[_resolve(opps, best.opp_col)])[best.opp_variant]
    lookup = pd.Series(opps.opp_id.values, index=ok.values)
    lookup = lookup[~lookup.index.isna()]
    lookup = lookup[~lookup.index.duplicated()]
    mapped = _variants(df[best.app_col])[best.app_variant].map(lookup).astype("string")
    log.append(f"Join: applications.{best.app_col} ({best.app_variant}) = opportunities.{best.opp_col} "
               f"({best.opp_variant}), {best.match_pct}% rows matched")
    return mapped


def load_applications(opps, log, raw=None, label="uploaded table"):
    if raw is None:
        _, path = find_files()
        if path is None:
            log.append("Applications: not provided -> sign-up / completion / lead-source metrics are OFF")
            return None
        raw = _read(path, cfg.APP_SHEET)
        label = Path(path).name
    log.append(f"Applications: {label} ({raw.shape[0]:,} rows x {raw.shape[1]} columns)")
    df = _clean_text(raw)
    C = cfg.APP_COLS

    dates = _first_date(df, C["date"])
    if dates is None:
        raise ValueError(f"Applications date column nahi mila ({C['date']}). Columns: {list(df.columns)}")
    out = pd.DataFrame({"app_opp_id": _match_opportunities(df, opps, C["opportunity_id"], log),
                        "app_date": dates}, index=df.index)

    # status + completion
    stc = _resolve(df, C.get("status"))
    out["app_status"] = df[stc] if stc else _na_series(df)
    if stc:
        top = df[stc].value_counts().head(8)
        log.append("Status values: " + ", ".join(f"{k}={v:,}" for k, v in top.items()))
    cc, cdc = _resolve(df, C.get("completed")), _resolve(df, C.get("completion_date"))
    if cc:
        out["app_completed"] = _to_bool(df[cc]).fillna(False).astype(bool)
        log.append(f"Completion = column '{cc}' is True")
    elif cdc:
        out["app_completed"] = _to_date(df[cdc]).notna().astype(bool)
        log.append(f"Completion = '{cdc}' is filled ({int(out.app_completed.sum()):,} rows)")
    elif stc:
        out["app_completed"] = df[stc].astype("string").str.lower().isin(cfg.COMPLETED_VALUES).fillna(False).astype(bool)
        log.append(f"Completion = status in {cfg.COMPLETED_VALUES} ({int(out.app_completed.sum()):,} rows)")
    else:
        out["app_completed"] = False
        log.append("WARNING: no completion information found -> completion rate OFF")

    # lead source: kai columns ko mila kar, text normalise
    ls = _first_text(df, C.get("lead_source"))
    if ls is not None:
        ls = ls.str.lower().str.replace(r"\s+", " ", regex=True).str.title()
        log.append(f"Lead source built from: {_resolve_many(df, C.get('lead_source'))}; "
                   f"{ls.nunique():,} distinct values, {int(ls.isna().sum()):,} missing")
    out["app_lead_source"] = (ls if ls is not None else _na_series(df)).fillna("Unknown")

    # duplicates (application id ke hisaab se, latest modified rakho)
    idc = _resolve(df, C.get("id"))
    if idc:
        out["app_id"] = _norm_id(df[idc])
        modc = _resolve(df, C.get("modified"))
        if modc:
            out = out.assign(_mod=_to_date(df[modc])).sort_values("_mod", kind="stable").drop(columns="_mod")
        n0 = len(out)
        dup = out.app_id.notna() & out.duplicated("app_id", keep="last")
        out = out[~dup].sort_index()
        log.append(f"Duplicate applications (same {idc}) removed: {n0 - len(out):,}")
    else:
        out["app_id"] = pd.Series(range(len(out)), index=out.index).astype("string")
        log.append("No application id column mapped -> duplicate applications NOT removed")

    unmatched = out.app_opp_id.isna()
    if unmatched.any():
        log.append(f"Applications not matching any opportunity (dropped): {int(unmatched.sum()):,}")
        out = out[~unmatched]
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


def load_all(opp_df=None, app_df=None):
    """opp_df/app_df do to uploaded tables use hongi, warna data/ folder ki files."""
    log = []
    if opp_df is not None:
        opps = load_opportunities(log, raw=opp_df)
        apps = load_applications(opps, log, raw=app_df) if app_df is not None else None
        if app_df is None:
            log.append("Applications: not provided -> sign-up / completion / lead-source metrics are OFF")
    else:
        opps = load_opportunities(log)
        apps = load_applications(opps, log)
    return {"opps": opps, "apps": apps, "log": log}
