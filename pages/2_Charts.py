import streamlit as st

from core import charts as ch
from core import detector as dt
from core import ui

name, df, prof = ui.setup("Charts", "📈")
df = ui.sidebar_filters(df, prof)
dims, meas, dates = dt.dimensions(prof, 60), dt.measures(prof), dt.cols(prof, "datetime")

tab1, tab2 = st.tabs(["Auto charts", "Chart builder"])
with tab1:
    st.caption("Charts chosen from the detected column types. Each one says why it is shown.")
    items = ch.auto_charts(df, prof)
    if not items:
        st.info("Not enough categorical, numeric or date columns for automatic charts.")
    for i in range(0, len(items), 2):
        cols = st.columns(2)
        for col, (title, fig, why) in zip(cols, items[i:i + 2]):
            col.plotly_chart(fig, key=f"auto_{i}_{title}")
            col.caption(why)

with tab2:
    types = ["Bar (top N)", "Pie", "Line over time", "Histogram", "Box", "Scatter", "Correlation heatmap", "Category x category heatmap"]
    kind = st.selectbox("Chart type", types)
    allc = list(df.columns)
    aggs = ["count", "sum", "mean", "median", "min", "max", "distinct"]
    fig = None
    if kind in ("Bar (top N)", "Pie"):
        c = st.columns(4)
        dim = c[0].selectbox("Group by", dims or allc)
        val = c[1].selectbox("Value (optional)", [None] + meas)
        agg = c[2].selectbox("Aggregation", aggs if val else ["count"])
        n = c[3].slider("Top N", 3, 30, 10)
        fig = ch.bar_top(df, dim, val, agg, n) if kind.startswith("Bar") else ch.pie_top(df, dim, val, agg, min(n, 12))
    elif kind == "Line over time":
        if not dates:
            st.warning("No date column detected.")
        else:
            c = st.columns(4)
            dcol = c[0].selectbox("Date", dates)
            grain = c[1].selectbox("Grain", ["Month", "Week", "Day", "Quarter", "Year"])
            val = c[2].selectbox("Value (optional)", [None] + meas)
            agg = c[3].selectbox("Aggregation", aggs if val else ["count"])
            fig = ch.line_ts(df, dcol, {"Day": "D", "Week": "W", "Month": "M", "Quarter": "Q", "Year": "Y"}[grain], val, agg)
    elif kind == "Histogram" and meas:
        fig = ch.histogram(df, st.selectbox("Column", meas), st.slider("Bins", 5, 100, 30))
    elif kind == "Box" and meas:
        c = st.columns(2)
        fig = ch.box(df, c[0].selectbox("Column", meas), c[1].selectbox("Split by (optional)", [None] + dims))
    elif kind == "Scatter" and len(meas) >= 2:
        c = st.columns(3)
        fig = ch.scatter(df, c[0].selectbox("X", meas), c[1].selectbox("Y", meas, index=1), c[2].selectbox("Colour by", [None] + dims))
    elif kind == "Correlation heatmap" and len(meas) >= 2:
        fig = ch.corr_heatmap(df, meas)
    elif kind == "Category x category heatmap" and len(dims) >= 2:
        c = st.columns(2)
        fig = ch.cross_heatmap(df, c[0].selectbox("Rows", dims), c[1].selectbox("Columns", dims, index=1))
    else:
        st.warning("This chart needs columns this table does not have (check the Overview > Schema tab).")
    if fig is not None:
        st.plotly_chart(fig, key="builder")
