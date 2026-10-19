import pandas as pd
import plotly.express as px
import streamlit as st

from core import analysis as an
from core import detector as dt
from core import measures as ms
from core import ui

name, df, prof = ui.setup("Measures & KPIs", "📐")
df = ui.sidebar_filters(df, prof)
dates, dims = dt.cols(prof, "datetime"), dt.dimensions(prof, 60)

st.session_state.setdefault("custom_measures", {})
mine = st.session_state["custom_measures"].setdefault(name, [])
suggested = ms.suggest_measures(df, prof)
allm = suggested + mine

st.subheader("Measure library")
st.caption("Auto-suggested measures plus the ones you create below. Every measure can be sliced by any field or by time.")
lib = pd.DataFrame([{"measure": m["name"], "definition": ms.describe(m), "value": ms.evaluate(df, m),
                     "source": "custom" if m in mine else "auto"} for m in allm])
st.dataframe(lib.style.format({"value": "{:,.2f}"}), hide_index=True)

with st.expander("Create a measure"):
    kind = st.radio("Type", ["Aggregate", "Ratio (% of ...)"], horizontal=True)
    cols = [None] + list(df.columns)

    def spec_form(prefix, default_agg="count rows"):
        c = st.columns(3)
        agg = c[0].selectbox("Aggregation", ms.AGGS, index=ms.AGGS.index(default_agg), key=f"{prefix}_agg")
        col = c[1].selectbox("Column", cols, key=f"{prefix}_col")
        nf = c[2].number_input("Filters", 0, 3, 0, key=f"{prefix}_nf")
        fl = []
        for i in range(int(nf)):
            f = st.columns(3)
            fc = f[0].selectbox("Filter column", list(df.columns), key=f"{prefix}_fc{i}")
            fo = f[1].selectbox("Operator", ms.OPS, key=f"{prefix}_fo{i}")
            fv = f[2].text_input("Value (comma-separated for 'in')", key=f"{prefix}_fv{i}")
            fl.append({"column": fc, "op": fo, "value": fv})
        return {"agg": agg, "column": col, "filters": fl}

    mname = st.text_input("Measure name")
    if kind == "Aggregate":
        spec = {"type": "aggregate", **spec_form("a")}
    else:
        st.markdown("**Numerator**")
        num = spec_form("n")
        st.markdown("**Denominator**")
        den = spec_form("d")
        spec = {"type": "ratio", "numerator": num, "denominator": den, "percent": st.checkbox("Show as percent", True)}
    if st.button("Add measure") and mname:
        try:
            v = ms.evaluate(df, {"name": mname, **spec})
            mine.append({"name": mname, **spec})
            st.success(f"Added. Current value: {v:,.2f}")
            st.rerun()
        except Exception as e:
            st.error(f"Could not evaluate: {e}")

st.subheader("Slice a measure")
c = st.columns(3)
pick = c[0].selectbox("Measure", [m["name"] for m in allm])
by = c[1].selectbox("Slice by", ["(over time)"] + dims)
grain = c[2].selectbox("Time grain", ["Month", "Week", "Day", "Quarter", "Year"]) if by == "(over time)" else None
m = next(x for x in allm if x["name"] == pick)
if by == "(over time)":
    if not dates:
        st.warning("No date column detected.")
        st.stop()
    dcol = st.selectbox("Date column", dates, index=dates.index(dt.primary_date(df, prof)))
    key = df[dcol].dt.to_period(an.FREQ[grain]).astype(str).where(df[dcol].notna())
    res = ms.evaluate_by(df, m, key, max_groups=500).sort_values("group")
    fig = px.line(res, x="group", y="value", markers=True, title=f"{pick} by {grain.lower()}")
else:
    res = ms.evaluate_by(df, m, by).sort_values("value", ascending=False)
    fig = px.bar(res.head(20), x="value", y="group", orientation="h", title=f"{pick} by {by}")
    fig.update_yaxes(categoryorder="total ascending")
st.plotly_chart(fig)
st.dataframe(res, hide_index=True)
st.caption("'rows' = number of records in that group. Small groups give unstable ratios.")
