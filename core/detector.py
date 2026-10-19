"""Har column ka role auto-detect karna: id / datetime / measure / category / boolean / text / label ..."""
import re

import numpy as np
import pandas as pd

CODE_NAME = re.compile(r"(code|status|type|level|grade|flag|class|cohort|group|categor|rating|rank|stage|tier)", re.I)
ID_NAME = re.compile(r"(^|_)(id|pk|sk|uuid|guid|key|ref|reference|code)$|^id$|_id_", re.I)
MONEY_NAME = re.compile(r"(fee|price|amount|cost|revenue|sales|salary|reward|paid|budget|income|profit|total|payment)", re.I)
PCT_NAME = re.compile(r"(percent|pct|rate|ratio|share)", re.I)
PRIMARY_DATE_NAME = re.compile(r"(created|apply|applied|order|signup|sign_up|start|date)", re.I)
BOOL_TOKENS = {"true", "false", "yes", "no", "y", "n", "0", "1", "t", "f"}
URL = re.compile(r"^(https?://|www\.)", re.I)
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$", re.I)

ROLES = ["id", "datetime", "measure", "category", "boolean", "label", "text", "url", "email", "json", "constant", "empty"]


def _is_text(s):
    return str(s.dtype) in ("object", "string", "str")


def column_role(name, s):
    n = len(s)
    nn = s.dropna()
    k = len(nn)
    if k == 0:
        return "empty", ""
    nu = nn.nunique()
    if pd.api.types.is_datetime64_any_dtype(s):
        return "datetime", ""
    if nu == 1 and n > 1:
        return "constant", ""
    if pd.api.types.is_bool_dtype(s):
        return "boolean", ""

    if pd.api.types.is_numeric_dtype(s):
        integer_like = bool((nn % 1 == 0).all())
        if nu == 2 and set(nn.unique()) <= {0, 1}:
            return "boolean", ""
        if (ID_NAME.search(name) and nu / k > 0.5) or (integer_like and nu == k and k > 20 and nn.is_monotonic_increasing):
            return "id", ""
        if integer_like and nu <= 6 and CODE_NAME.search(name):
            return "category", "numeric code"
        hint = "money" if MONEY_NAME.search(name) else "percent" if PCT_NAME.search(name) else ""
        return "measure", hint

    low = nn.astype(str).str.strip().str.lower()
    if nu <= 2 and set(low.unique()) <= BOOL_TOKENS:
        return "boolean", ""
    head = low.head(300)
    if head.str.match(URL).mean() > 0.8:
        return "url", ""
    if head.str.match(EMAIL).mean() > 0.8:
        return "email", ""
    if head.str.startswith(("{", "[")).mean() > 0.6:
        return "json", ""
    avg_len = nn.astype(str).str.len().mean()
    if ID_NAME.search(name) and nu / k > 0.5:
        return "id", ""
    if avg_len > 60:
        return "text", ""
    if nu <= max(30, int(0.05 * k)):
        return "category", ""
    if nu / k > 0.9:
        code_like = nn.astype(str).str.match(r"^[\w\-#:./]+$").mean() > 0.95 and avg_len < 40
        return ("id", "") if code_like and not re.search(r"name|title", name, re.I) else ("label", "")
    return "category", "high cardinality"


def detect_roles(df):
    rows = []
    for c in df.columns:
        s = df[c]
        role, hint = column_role(c, s)
        nn = s.dropna()
        r = {"column": c, "dtype": str(s.dtype), "role": role, "hint": hint,
             "missing_pct": round(float(s.isna().mean() * 100), 1), "unique": int(nn.nunique()) if len(nn) else 0}
        r["unique_pct"] = round(r["unique"] / max(len(nn), 1) * 100, 1)
        if role == "measure":
            r.update(min=float(nn.min()), max=float(nn.max()), mean=round(float(nn.mean()), 2))
        elif role == "datetime":
            r.update(min=str(nn.min())[:10], max=str(nn.max())[:10])
        r["sample"] = ", ".join(nn.astype(str).drop_duplicates().head(3).str.slice(0, 30))
        rows.append(r)
    return pd.DataFrame(rows)


def cols(prof, *roles):
    return prof.loc[prof.role.isin(roles), "column"].tolist()


def measures(prof):
    """Measures: money wale pehle, phir baqi."""
    m = prof[prof.role == "measure"].copy()
    m["_k"] = m.hint.map({"money": 0, "percent": 2}).fillna(1)
    return m.sort_values(["_k", "missing_pct"]).column.tolist()


def dimensions(prof, max_unique=40):
    d = prof[(prof.role.isin(["category", "boolean"])) & (prof.unique <= max_unique) & (prof.unique >= 2)]
    return d.sort_values(["missing_pct", "unique"]).column.tolist()


def primary_date(df, prof):
    d = prof[prof.role == "datetime"]
    if d.empty:
        return None
    score = (100 - d.missing_pct) + d.column.map(lambda c: 30 if PRIMARY_DATE_NAME.search(c) else 0)
    return d.loc[score.idxmax(), "column"]


def primary_id(prof):
    ids = prof[prof.role == "id"]
    if ids.empty:
        return None
    full = ids[ids.unique_pct >= 99]
    return (full if not full.empty else ids).iloc[0]["column"]


def schema_summary(prof):
    return prof.role.value_counts().to_dict()
