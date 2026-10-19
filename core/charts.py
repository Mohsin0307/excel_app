"""Plotly charts + auto chart suggestions (har chart ke saath 'kyun' bhi)."""
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from . import analysis as an
from . import detector as dt

BLUE = "#2E75B6"
LAYOUT = dict(margin=dict(l=0, r=10, t=50, b=0), height=380)


def _fin(fig, **kw):
    fig.update_layout(**{**LAYOUT, **kw})
    return fig


def bar_top(df, dim, value=None, agg="count", n=10, title=None, horizontal=True):
    t = an.top_n(df, dim, value, agg, n)
    label = "records" if agg == "count" or value is None else f"{agg} of {value}"
    title = title or f"Top {len(t)} {dim} by {label}"
    if horizontal:
        fig = px.bar(t, x="value", y=dim, orientation="h", text="value", title=title, color_discrete_sequence=[BLUE])
        fig.update_yaxes(categoryorder="total ascending", title=None)
    else:
        fig = px.bar(t, x=dim, y="value", text="value", title=title, color_discrete_sequence=[BLUE])
    fig.update_traces(texttemplate="%{text:,.2s}" if t.value.max() > 9999 else "%{text:,.1f}" if agg in ("mean", "median") else "%{text:,}")
    return _fin(fig, xaxis_title=None if horizontal else dim)


def pie_top(df, dim, value=None, agg="count", n=8, title=None):
    s = an.aggregate(df, dim, value, agg).sort_values(ascending=False)
    if len(s) > n:
        s = pd.concat([s.head(n), pd.Series({"Other": s.iloc[n:].sum()})])
    fig = px.pie(names=s.index.astype(str), values=s.values, hole=0.4, title=title or f"{dim}: share (top {n} + Other)")
    return _fin(fig)


def histogram(df, col, bins=30):
    return _fin(px.histogram(df.dropna(subset=[col]), x=col, nbins=bins, title=f"Distribution of {col}",
                             color_discrete_sequence=[BLUE]))


def box(df, col, by=None):
    d = df.dropna(subset=[col])
    if by:
        top = d[by].value_counts().head(12).index
        d = d[d[by].isin(top)]
    return _fin(px.box(d, y=col, x=by, title=f"{col}" + (f" by {by}" if by else ""), color_discrete_sequence=[BLUE]))


def line_ts(df, date_col, freq="M", value=None, agg="count", title=None):
    ts = an.time_series(df, date_col, freq, value, agg)
    label = "records" if agg == "count" or value is None else f"{agg} of {value}"
    fig = px.line(ts, x="period", y="value", markers=True, title=title or f"{label.title()} over time ({date_col})")
    fig.update_traces(line_color=BLUE)
    return _fin(fig, xaxis_title=None, yaxis_title=label)


def area_ts(df, date_col, dim, freq="M", n=6):
    d = df.dropna(subset=[date_col]).copy()
    top = d[dim].value_counts().head(n).index
    d[dim] = d[dim].where(d[dim].isin(top), "Other")
    d["_p"] = d[date_col].dt.to_period(freq).dt.start_time
    t = d.groupby(["_p", dim]).size().reset_index(name="records")
    return _fin(px.area(t, x="_p", y="records", color=dim, title=f"Records over time by {dim}"), xaxis_title=None)


def scatter(df, x, y, color=None):
    d = df.dropna(subset=[x, y])
    if len(d) > 5000:
        d = d.sample(5000, random_state=0)
    return _fin(px.scatter(d, x=x, y=y, color=color, opacity=0.6, title=f"{y} vs {x}", color_discrete_sequence=[BLUE]))


def corr_heatmap(df, meas):
    meas = [c for c in meas if df[c].nunique() > 3][:20]
    c = df[meas].corr(method="spearman")
    return _fin(px.imshow(c, text_auto=".2f", color_continuous_scale="RdBu", zmin=-1, zmax=1, title="Correlation (Spearman)"),
                height=max(380, 40 * len(meas)))


def cross_heatmap(df, a, b, n=12):
    ta, tb = df[a].value_counts().head(n).index, df[b].value_counts().head(n).index
    ct = pd.crosstab(df[a], df[b]).reindex(index=ta, columns=tb).fillna(0)
    return _fin(px.imshow(ct, text_auto=True, color_continuous_scale="Blues", title=f"{a} x {b} (record counts)", aspect="auto"))


def funnel(ms):
    fig = go.Figure(go.Funnel(y=ms.stage, x=ms.records, textinfo="value+percent initial", marker_color=BLUE))
    fig.update_layout(title="Stage funnel (non-blank dates per column)", **LAYOUT)
    return fig


def auto_charts(df, prof, max_charts=12):
    """[(title, figure, why)]"""
    out = []
    pdate = dt.primary_date(df, prof)
    dims = dt.dimensions(prof, 40)
    meas = dt.measures(prof)
    if pdate:
        out.append((f"Records over time", line_ts(df, pdate, "M"), f"Shows momentum and seasonality using '{pdate}'."))
    for d in dims[:3]:
        k = prof.loc[prof.column == d, "unique"].iloc[0]
        fig = pie_top(df, d) if k <= 6 else bar_top(df, d)
        out.append((f"{d} breakdown", fig, f"Shows how records are split across '{d}'."))
    for m in meas[:3]:
        out.append((f"Distribution of {m}", histogram(df, m), f"Shows the spread, skew and typical range of '{m}'."))
    if meas and dims:
        out.append((f"{meas[0]} by {dims[0]}", bar_top(df, dims[0], meas[0], "mean", 10, horizontal=True),
                    f"Compares the average '{meas[0]}' across '{dims[0]}'."))
    pairs = an.correlation_pairs(df, meas)
    if len(pairs):
        r = pairs.iloc[0]
        out.append((f"{r.b} vs {r.a}", scatter(df, r.a, r.b), f"Strongest relationship found (r = {r.r:.2f})."))
    if pdate and dims:
        out.append((f"Over time by {dims[0]}", area_ts(df, pdate, dims[0]), f"Shows whether the mix of '{dims[0]}' changes over time."))
    ms = an.milestones(df, prof)
    if len(ms) >= 2:
        out.append(("Stage funnel", funnel(ms), "Date columns look like process stages; shows drop-off."))
    return out[:max_charts]
