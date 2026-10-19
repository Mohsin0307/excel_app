"""Pivot table engine (Excel jaisa): rows, columns, value, aggregation, % of total, date grouping, export."""
import io

import numpy as np
import pandas as pd

AGGS = ["count", "distinct count", "sum", "mean", "median", "min", "max"]
GRAINS = {"Day": "D", "Week": "W", "Month": "M", "Quarter": "Q", "Year": "Y"}
SHOW = ["Value", "% of grand total", "% of row total", "% of column total"]


def with_date_part(df, col, grain):
    """Date column ko Month/Quarter/Year label mein badal kar naya column banao."""
    name = f"{col} ({grain})"
    out = df.copy()
    out[name] = out[col].dt.to_period(GRAINS[grain]).astype(str).where(out[col].notna())
    return out, name


def build_pivot(df, rows, cols=None, value=None, agg="count", show="Value", margins=True, top_rows=None):
    if not rows:
        raise ValueError("Pick at least one row field.")
    d = df.copy()
    for c in rows + (cols or []):
        if not pd.api.types.is_datetime64_any_dtype(d[c]):
            d[c] = d[c].astype("object").where(d[c].notna(), "(blank)")
        else:
            d[c] = d[c].dt.strftime("%Y-%m-%d").fillna("(blank)")
    if agg == "count" or value is None:
        d["_n"], value, func = 1, "_n", "sum"
    else:
        func = {"distinct count": "nunique"}.get(agg, agg)
    pv = pd.pivot_table(d, index=rows, columns=cols or None, values=value, aggfunc=func, observed=True, fill_value=0 if func in ("sum", "nunique") else np.nan)
    if isinstance(pv, pd.Series):
        pv = pv.to_frame(value)
    if show != "Value":
        if func not in ("sum", "nunique"):
            raise ValueError("Percent views only make sense for count / sum / distinct count.")
        if show == "% of grand total":
            pv = pv / pv.values.sum() * 100
        elif show == "% of row total":
            pv = pv.div(pv.sum(axis=1), axis=0) * 100
        else:
            pv = pv.div(pv.sum(axis=0), axis=1) * 100
        pv = pv.round(2)
    if top_rows:
        order = pv.sum(axis=1).sort_values(ascending=False).index[:top_rows]
        pv = pv.loc[order]
    if margins and show == "Value" and func in ("sum", "nunique"):
        pv = pv.copy()
        if pv.shape[1] > 1:
            pv["Total"] = pv.sum(axis=1)
        pv.loc[("Total",) * pv.index.nlevels if pv.index.nlevels > 1 else "Total"] = pv.sum(axis=0)
    elif margins and show == "Value":
        pass  # mean/median margins ambiguous: skip
    pv.columns = [" | ".join(map(str, c)) if isinstance(c, tuple) else str(c) for c in pv.columns]
    return pv


def to_excel_bytes(sheets):
    """{name: DataFrame} -> .xlsx bytes."""
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        for name, df in sheets.items():
            df.to_excel(w, sheet_name=str(name)[:31], index=not isinstance(df.index, pd.RangeIndex))
    return buf.getvalue()
