"""KPIs, trends, correlations, associations, outliers, concentration, insights (sab auto)."""
import re

import numpy as np
import pandas as pd

from . import detector as dt

SYSTEM_TS = re.compile(r"(created|modified|updated|inserted|last_?edit|last_?seen)", re.I)
FREQ = {"Day": "D", "Week": "W", "Month": "M", "Quarter": "Q", "Year": "Y"}


# ---------------------------------------------------------------- aggregation helpers
def aggregate(df, group, value=None, agg="count"):
    """group = column ya Series. agg: count / distinct / sum / mean / median / min / max."""
    key = df[group] if isinstance(group, str) else group
    key = key.astype("object").where(key.notna(), "(blank)")
    if agg == "count" or value is None:
        return df.groupby(key, observed=True).size()
    g = df.groupby(key, observed=True)[value]
    return {"distinct": g.nunique, "sum": g.sum, "mean": g.mean, "median": g.median, "min": g.min, "max": g.max}[agg]()


def top_n(df, dim, value=None, agg="count", n=10, ascending=False):
    s = aggregate(df, dim, value, agg).sort_values(ascending=ascending).head(n)
    out = s.rename("value").reset_index()
    out.columns = [dim, "value"]
    return out


def time_series(df, date_col, freq="M", value=None, agg="count"):
    d = df.dropna(subset=[date_col])
    if d.empty:
        return pd.DataFrame({"period": [], "value": []})
    p = d[date_col].dt.to_period(freq)
    if agg == "count" or value is None:
        s = d.groupby(p).size()
    else:
        s = getattr(d.groupby(p)[value], {"distinct": "nunique"}.get(agg, agg))()
    idx = pd.period_range(p.min(), p.max(), freq=freq)
    s = s.reindex(idx, fill_value=0 if agg in ("count", "sum", "distinct") else np.nan)
    return pd.DataFrame({"period": idx.start_time, "value": s.values})


# ---------------------------------------------------------------- KPI cards
def _fmt(x):
    if pd.isna(x):
        return "n/a"
    if abs(x) >= 1e9:
        return f"{x / 1e9:.2f}B"
    if abs(x) >= 1e6:
        return f"{x / 1e6:.2f}M"
    if abs(x) >= 1e4:
        return f"{x / 1e3:.1f}K"
    return f"{x:,.0f}" if float(x).is_integer() else f"{x:,.2f}"


def kpi_cards(df, prof):
    cards = [{"label": "Rows", "value": f"{len(df):,}"}, {"label": "Columns", "value": f"{df.shape[1]}"}]
    cards.append({"label": "Completeness", "value": f"{(1 - df.isna().mean().mean()) * 100:.1f}%",
                  "help": "Share of cells that are not empty"})
    pid = dt.primary_id(prof)
    if pid:
        cards.append({"label": f"Distinct {pid}", "value": f"{df[pid].nunique():,}"})
    pdate = dt.primary_date(df, prof)
    if pdate:
        ts = time_series(df, pdate, "M")
        if len(ts) >= 2 and ts.value.iloc[-2] > 0:
            ch = (ts.value.iloc[-1] - ts.value.iloc[-2]) / ts.value.iloc[-2] * 100
            cards.append({"label": f"Records in {ts.period.iloc[-1]:%b %Y}", "value": f"{int(ts.value.iloc[-1]):,}",
                          "delta": f"{ch:+.1f}% vs previous month",
                          "help": f"Counted by {pdate}; latest month may be partial"})
    for c in dt.measures(prof)[:3]:
        hint = prof.loc[prof.column == c, "hint"].iloc[0]
        if hint == "money":
            cards.append({"label": f"Total {c}", "value": _fmt(df[c].sum())})
        cards.append({"label": f"Avg {c}", "value": _fmt(df[c].mean())})
    for c in dt.dimensions(prof, 12)[:2]:
        vc = df[c].value_counts(normalize=True)
        if len(vc):
            cards.append({"label": f"Top {c}", "value": str(vc.index[0])[:24], "delta": f"{vc.iloc[0] * 100:.1f}% of rows",
                          "delta_color": "off"})
    return cards[:12]


# ---------------------------------------------------------------- patterns
def correlation_pairs(df, meas, min_abs=0.5, max_cols=25):
    meas = [c for c in meas if df[c].nunique() > 3][:max_cols]
    if len(meas) < 2:
        return pd.DataFrame(columns=["a", "b", "r"])
    corr = df[meas].corr(method="spearman")
    rows = [(a, b, corr.loc[a, b]) for i, a in enumerate(meas) for b in meas[i + 1:] if pd.notna(corr.loc[a, b])]
    out = pd.DataFrame(rows, columns=["a", "b", "r"])
    out = out[out.r.abs() >= min_abs].assign(abs_r=lambda d: d.r.abs()).sort_values("abs_r", ascending=False)
    return out.drop(columns="abs_r").reset_index(drop=True)


def cramers_v(a, b):
    ct = pd.crosstab(a, b)
    if ct.shape[0] < 2 or ct.shape[1] < 2:
        return np.nan
    obs = ct.values.astype(float)
    exp = obs.sum(1, keepdims=True) * obs.sum(0, keepdims=True) / obs.sum()
    chi2 = ((obs - exp) ** 2 / exp).sum()
    return float(np.sqrt(chi2 / (obs.sum() * (min(obs.shape) - 1))))


def category_associations(df, dims, min_v=0.3, max_dims=12):
    dims = dims[:max_dims]
    rows = []
    for i, a in enumerate(dims):
        for b in dims[i + 1:]:
            d = df[[a, b]].dropna()
            if len(d) < 30:
                continue
            v = cramers_v(d[a], d[b])
            if pd.notna(v) and v >= min_v:
                rows.append((a, b, round(v, 2)))
    return pd.DataFrame(rows, columns=["a", "b", "cramers_v"]).sort_values("cramers_v", ascending=False, ignore_index=True)


def eta_squared(cat, num):
    d = pd.DataFrame({"c": cat, "n": num}).dropna()
    if len(d) < 30 or d.c.nunique() < 2:
        return np.nan
    tot = ((d.n - d.n.mean()) ** 2).sum()
    if tot == 0:
        return np.nan
    g = d.groupby("c").n.agg(["count", "mean"])
    return float((g["count"] * (g["mean"] - d.n.mean()) ** 2).sum() / tot)


def category_drivers(df, dims, meas, min_eta=0.1, max_pairs=60):
    rows = []
    for c in dims[:10]:
        for m in meas[:6]:
            e = eta_squared(df[c], df[m])
            if pd.notna(e) and e >= min_eta:
                rows.append((c, m, round(e, 3)))
    return pd.DataFrame(rows, columns=["category", "measure", "eta_squared"]).sort_values(
        "eta_squared", ascending=False, ignore_index=True).head(max_pairs)


def outlier_summary(df, meas):
    rows = []
    for c in meas:
        s = df[c].dropna()
        if len(s) < 20:
            continue
        q1, q3 = s.quantile([0.25, 0.75])
        iqr = q3 - q1
        lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        n = int(((s < lo) | (s > hi)).sum())
        rows.append({"column": c, "outliers": n, "outlier_pct": round(n / len(s) * 100, 2),
                     "lower_fence": round(lo, 2), "upper_fence": round(hi, 2), "max": s.max(), "min": s.min()})
    return pd.DataFrame(rows).sort_values("outlier_pct", ascending=False, ignore_index=True) if rows else pd.DataFrame()


def concentration(df, dim, value=None):
    df = df.dropna(subset=[dim])
    s = aggregate(df, dim, value, "sum" if value else "count").sort_values(ascending=False)
    s = s[s > 0]
    if len(s) < 3:
        return None
    top20 = max(1, int(np.ceil(len(s) * 0.2)))
    return {"categories": len(s), "top1": s.index[0], "top1_share": s.iloc[0] / s.sum() * 100,
            "top20_share": s.head(top20).sum() / s.sum() * 100, "top20_n": top20}


def trend_summary(ts):
    """ts: DataFrame(period, value). Slope, last-vs-previous, peak, anomalies."""
    if len(ts) < 4:
        return None
    y = ts.value.astype(float).values
    slope = np.polyfit(np.arange(len(y)), y, 1)[0]
    mean = y.mean() or np.nan
    z = (y - y.mean()) / (y.std() or np.nan)
    return {"slope_pct_per_period": slope / mean * 100 if mean else np.nan,
            "peak": ts.period.iloc[int(y.argmax())], "peak_value": y.max(),
            "low": ts.period.iloc[int(y.argmin())], "low_value": y.min(),
            "anomalies": ts.period[np.abs(np.nan_to_num(z)) > 2.5].tolist()}


def weekday_pattern(df, date_col):
    d = df[date_col].dropna()
    if len(d) < 50 or d.dt.normalize().nunique() < 14:
        return None
    c = d.dt.day_name().value_counts().reindex(
        ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]).fillna(0)
    return c


def milestones(df, prof):
    """Date columns ka non-blank count (funnel): kitne records ne har stage touch ki."""
    dc = [c for c in dt.cols(prof, "datetime") if not SYSTEM_TS.search(c)]
    if len(dc) < 2:
        return pd.DataFrame()
    t = pd.DataFrame({"stage": dc, "records": [int(df[c].notna().sum()) for c in dc]})
    t["pct_of_rows"] = (t.records / len(df) * 100).round(1)
    return t.sort_values("records", ascending=False, ignore_index=True)


def missing_groups(df, min_missing=1.0, min_corr=0.95):
    """Columns jo hamesha saath saath khali hoti hain (ek hi wajah se)."""
    cols = [c for c in df.columns if df[c].isna().mean() * 100 >= min_missing and df[c].notna().any()][:60]
    if len(cols) < 2:
        return []
    m = df[cols].isna().astype(int).corr()
    seen, groups = set(), []
    for c in cols:
        if c in seen:
            continue
        g = [x for x in cols if x not in seen and pd.notna(m.loc[c, x]) and m.loc[c, x] >= min_corr]
        if len(g) > 1:
            groups.append(g)
            seen.update(g)
    return groups


# ---------------------------------------------------------------- insights
def generate_insights(df, prof):
    out = []

    def add(kind, text):
        out.append({"type": kind, "insight": text})

    n = len(df)
    empty = dt.cols(prof, "empty")
    if empty:
        add("quality", f"{len(empty)} column(s) are completely empty and can be ignored: {', '.join(empty[:8])}.")
    const = dt.cols(prof, "constant")
    if const:
        add("quality", f"{len(const)} column(s) have a single value for every row: {', '.join(const[:8])}.")
    hi = prof[(prof.missing_pct >= 40) & (prof.role != "empty")]
    if len(hi):
        add("quality", f"{len(hi)} column(s) are more than 40% empty (e.g. {', '.join(hi.column.head(5))}). Check whether they are optional fields.")
    for g in missing_groups(df)[:3]:
        add("quality", f"These columns are empty together, probably one shared cause: {', '.join(g[:6])}.")
    dup = df.duplicated().mean() * 100
    if dup > 0:
        add("quality", f"{dup:.1f}% of rows are exact duplicates.")

    pid = dt.primary_id(prof)
    if pid and df[pid].duplicated().any():
        add("quality", f"'{pid}' looks like an ID but {int(df[pid].duplicated().sum()):,} values repeat. Check for duplicate records.")

    pdate = dt.primary_date(df, prof)
    if pdate:
        ts = time_series(df, pdate, "M")
        ts_s = trend_summary(ts)
        if ts_s:
            direction = "growing" if ts_s["slope_pct_per_period"] > 3 else "declining" if ts_s["slope_pct_per_period"] < -3 else "roughly flat"
            add("trend", f"Monthly records by '{pdate}' are {direction} ({ts_s['slope_pct_per_period']:+.1f}% per month on average). "
                         f"Peak: {ts_s['peak']:%b %Y} ({ts_s['peak_value']:,.0f}); lowest: {ts_s['low']:%b %Y} ({ts_s['low_value']:,.0f}).")
            if ts_s["anomalies"]:
                add("trend", "Unusual months (more than 2.5 standard deviations from normal): "
                             + ", ".join(f"{a:%b %Y}" for a in ts_s["anomalies"][:5]) + ".")
        wd = weekday_pattern(df, pdate)
        if wd is not None and wd.max() > 1.5 * wd.mean():
            add("pattern", f"{wd.idxmax()} is the busiest weekday ({wd.max() / wd.sum() * 100:.0f}% of records vs {100 / 7:.0f}% if even).")

    ms = milestones(df, prof)
    if len(ms) >= 2:
        add("pattern", "Date columns behave like stages: " + " -> ".join(
            f"{r.stage} ({r.pct_of_rows:.0f}%)" for r in ms.itertuples()) + ". Drop-offs between stages are worth studying.")

    dims = dt.dimensions(prof, 30)
    meas = dt.measures(prof)
    money = meas[0] if meas and prof.loc[prof.column == meas[0], "hint"].iloc[0] == "money" else None
    for d in dims[:4]:
        c = concentration(df, d, money)
        if not c:
            continue
        what = f"of total {money}" if money else "of records"
        if c["categories"] >= 8 and c["top20_share"] >= 80:
            add("pattern", f"'{d}' is concentrated: the top {c['top20_n']} of {c['categories']} values hold {c['top20_share']:.0f}% {what}.")
        elif c["top1_share"] >= 40:
            add("pattern", f"'{d}': '{c['top1']}' alone accounts for {c['top1_share']:.0f}% {what}.")
    for r in correlation_pairs(df, meas).head(4).itertuples():
        add("pattern", f"'{r.a}' and '{r.b}' move {'together' if r.r > 0 else 'in opposite directions'} (Spearman r = {r.r:.2f}).")
    for r in category_associations(df, dims).head(3).itertuples():
        add("pattern", f"'{r.a}' and '{r.b}' are strongly linked (Cramer's V = {r.cramers_v}).")
    for r in category_drivers(df, dims, meas).head(3).itertuples():
        add("pattern", f"'{r.category}' explains {r.eta_squared * 100:.0f}% of the variation in '{r.measure}'.")
    o = outlier_summary(df, meas[:6])
    if len(o) and o.outlier_pct.iloc[0] >= 2:
        add("quality", f"'{o.column.iloc[0]}' has {o.outliers.iloc[0]:,} outliers ({o.outlier_pct.iloc[0]}%), "
                       f"values outside {o.lower_fence.iloc[0]:,} to {o.upper_fence.iloc[0]:,}.")
    return out
