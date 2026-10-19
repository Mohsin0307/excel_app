"""
Measures (DAX-light): naam wali calculations jo kisi bhi dimension ya time ke hisaab se nikal sakti hain.

Aggregate measure : {"name", "type": "aggregate", "agg", "column", "filters": [...]}
Ratio measure     : {"name", "type": "ratio", "numerator": {agg, column, filters}, "denominator": {...}, "percent": True}
Filter            : {"column", "op", "value"}
"""
import numpy as np
import pandas as pd

from . import detector as dt

AGGS = ["count rows", "count non-blank", "distinct count", "sum", "mean", "median", "min", "max"]
OPS = ["=", "!=", ">", ">=", "<", "<=", "in", "contains", "is blank", "is not blank"]


def apply_filters(df, filters):
    mask = pd.Series(True, index=df.index)
    for f in filters or []:
        s, op, v = df[f["column"]], f["op"], f.get("value")
        if op == "is blank":
            m = s.isna()
        elif op == "is not blank":
            m = s.notna()
        elif op == "contains":
            m = s.astype("string").str.contains(str(v), case=False, na=False, regex=False)
        elif op == "in":
            vals = [x.strip() for x in str(v).split(",")]
            m = s.astype("string").isin(vals)
        else:
            if pd.api.types.is_numeric_dtype(s):
                v = float(v)
            elif pd.api.types.is_datetime64_any_dtype(s):
                v = pd.Timestamp(v)
            else:
                s, v = s.astype("string"), str(v)
            m = {"=": s == v, "!=": s != v, ">": s > v, ">=": s >= v, "<": s < v, "<=": s <= v}[op]
        mask &= m.fillna(False)
    return df[mask]


def _agg(d, spec):
    a, c = spec["agg"], spec.get("column")
    if a == "count rows" or not c:
        return float(len(d))
    s = d[c]
    if a == "count non-blank":
        return float(s.notna().sum())
    if a == "distinct count":
        return float(s.nunique())
    if not pd.api.types.is_numeric_dtype(s):
        return np.nan
    return float(getattr(s, a)()) if len(s.dropna()) else np.nan


def _value(df, m):
    if m["type"] == "ratio":
        num = _agg(apply_filters(df, m["numerator"].get("filters")), m["numerator"])
        den = _agg(apply_filters(df, m["denominator"].get("filters")), m["denominator"])
        if not den:
            return np.nan
        return num / den * (100 if m.get("percent", True) else 1)
    return _agg(apply_filters(df, m.get("filters")), m)


def evaluate(df, m):
    return _value(df, m)


def evaluate_by(df, m, key, max_groups=60):
    """key = column naam ya Series (jaise month label). Return DataFrame(group, value, rows)."""
    k = df[key] if isinstance(key, str) else key
    k = k.astype("object").where(k.notna(), "(blank)")
    sizes = k.value_counts()
    keep = sizes.index[:max_groups]
    rows = [{"group": g, "value": _value(df[k == g], m), "rows": int(sizes[g])} for g in keep]
    return pd.DataFrame(rows)


def describe(m):
    def part(s):
        t = f"{s['agg']}" + (f" of {s['column']}" if s.get("column") else "")
        for f in s.get("filters", []) or []:
            t += f" where {f['column']} {f['op']} {f.get('value', '')}".rstrip()
        return t
    if m["type"] == "ratio":
        return f"({part(m['numerator'])}) / ({part(m['denominator'])})" + (" x 100" if m.get("percent", True) else "")
    return part(m)


def suggest_measures(df, prof):
    out = [{"name": "Total records", "type": "aggregate", "agg": "count rows", "column": None, "filters": []}]
    pid = dt.primary_id(prof)
    if pid:
        out.append({"name": f"Distinct {pid}", "type": "aggregate", "agg": "distinct count", "column": pid, "filters": []})
    for c in dt.measures(prof)[:5]:
        hint = prof.loc[prof.column == c, "hint"].iloc[0]
        for a in (["sum", "mean"] if hint == "money" else ["mean"]):
            out.append({"name": f"{a.title()} of {c}", "type": "aggregate", "agg": a, "column": c, "filters": []})
    allrows = {"agg": "count rows", "column": None, "filters": []}
    for c in dt.cols(prof, "boolean")[:4]:
        out.append({"name": f"% {c} = true", "type": "ratio", "percent": True, "denominator": allrows,
                    "numerator": {"agg": "count rows", "column": None,
                                  "filters": [{"column": c, "op": "in", "value": "True,true,1,1.0,Yes,yes,Y"}]}})
    dcols = dt.cols(prof, "datetime")
    pdate = dt.primary_date(df, prof)
    for c in [x for x in dcols if x != pdate][:6]:
        out.append({"name": f"% rows with {c}", "type": "ratio", "percent": True, "denominator": allrows,
                    "numerator": {"agg": "count rows", "column": None, "filters": [{"column": c, "op": "is not blank"}]}})
    for c in dt.dimensions(prof, 8)[:3]:
        for v in df[c].value_counts().head(3).index:
            out.append({"name": f"% {c} = {v}", "type": "ratio", "percent": True, "denominator": allrows,
                        "numerator": {"agg": "count rows", "column": None, "filters": [{"column": c, "op": "=", "value": str(v)}]}})
    return out
