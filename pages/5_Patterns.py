import streamlit as st

from core import analysis as an
from core import charts as ch
from core import detector as dt
from core import ui

name, df, prof = ui.setup("Patterns", "🔎")
df = ui.sidebar_filters(df, prof)
meas, dims = dt.measures(prof), dt.dimensions(prof, 30)
pdate = dt.primary_date(df, prof)

t = st.tabs(["Trends", "Relationships", "Concentration", "Funnel / stages", "Outliers"])
with t[0]:
    if not pdate:
        st.info("No date column detected.")
    else:
        grain = st.selectbox("Grain", ["Month", "Week", "Day", "Quarter"], index=0)
        ts = an.time_series(df, pdate, an.FREQ[grain])
        st.plotly_chart(ch.line_ts(df, pdate, an.FREQ[grain]), key="trend")
        s = an.trend_summary(ts)
        if s:
            st.write(f"Average change: **{s['slope_pct_per_period']:+.1f}% per {grain.lower()}**; peak {s['peak']:%Y-%m-%d} "
                     f"({s['peak_value']:,.0f}); low {s['low']:%Y-%m-%d} ({s['low_value']:,.0f}).")
            if s["anomalies"]:
                st.write("Unusual periods: " + ", ".join(f"{a:%Y-%m-%d}" for a in s["anomalies"][:8]))
        wd = an.weekday_pattern(df, pdate)
        if wd is not None:
            import plotly.express as px
            st.plotly_chart(px.bar(wd, title="Records by weekday", color_discrete_sequence=[ch.BLUE]).update_layout(showlegend=False), key="wd")
with t[1]:
    c = an.correlation_pairs(df, meas, min_abs=0.3)
    st.markdown("**Numeric relationships** (Spearman, |r| >= 0.3)")
    st.dataframe(c, hide_index=True) if len(c) else st.caption("None found.")
    a = an.category_associations(df, dims, min_v=0.2)
    st.markdown("**Category associations** (Cramer's V >= 0.2)")
    st.dataframe(a, hide_index=True) if len(a) else st.caption("None found.")
    d = an.category_drivers(df, dims, meas, min_eta=0.05)
    st.markdown("**Which category explains a numeric field** (eta squared >= 0.05)")
    st.dataframe(d, hide_index=True) if len(d) else st.caption("None found.")
    if len(meas) >= 2:
        st.plotly_chart(ch.corr_heatmap(df, meas), key="corr")
with t[2]:
    if not dims:
        st.info("No categorical column found.")
    else:
        d = st.selectbox("Field", dims)
        v = st.selectbox("Weight by (optional)", [None] + meas)
        c = an.concentration(df, d, v)
        if c:
            st.write(f"**{c['top1']}** is the biggest ({c['top1_share']:.1f}%). The top {c['top20_n']} of {c['categories']} values "
                     f"(top 20%) make up **{c['top20_share']:.1f}%**.")
        st.plotly_chart(ch.bar_top(df, d, v, "sum" if v else "count", 15), key="conc")
with t[3]:
    ms = an.milestones(df, prof)
    if ms.empty:
        st.info("Needs at least two date columns (e.g. apply_date, completion_date).")
    else:
        st.plotly_chart(ch.funnel(ms), key="fun")
        st.dataframe(ms, hide_index=True)
with t[4]:
    o = an.outlier_summary(df, meas)
    st.dataframe(o, hide_index=True) if len(o) else st.caption("No numeric columns.")
    if meas:
        st.plotly_chart(ch.box(df, st.selectbox("Column", meas)), key="box")
