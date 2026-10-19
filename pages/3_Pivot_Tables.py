import pandas as pd
import streamlit as st

from core import detector as dt
from core import pivot, ui

name, df, prof = ui.setup("Pivot Tables", "🧮")
df = ui.sidebar_filters(df, prof)

dates = dt.cols(prof, "datetime")
usable = [c for c in df.columns if prof.set_index("column").loc[c, "role"] in ("category", "boolean", "datetime", "label", "id")]
meas = dt.measures(prof)

c = st.columns(3)
rows = c[0].multiselect("Rows", usable, default=dt.dimensions(prof, 40)[:1])
cols_ = c[1].multiselect("Columns", usable, max_selections=2)
agg = c[2].selectbox("Aggregation", pivot.AGGS)
c = st.columns(4)
value = c[0].selectbox("Value field (needed unless Count)", [None] + meas + [x for x in df.columns if x not in meas])
show = c[1].selectbox("Show as", pivot.SHOW)
top = c[2].number_input("Top rows (0 = all)", 0, 1000, 20)
margins = c[3].checkbox("Grand totals", True)

d = df
if dates:
    with st.expander("Group a date column (Day / Month / Quarter / Year)"):
        cc = st.columns(3)
        dcol = cc[0].selectbox("Date column", [None] + dates)
        grain = cc[1].selectbox("Group by", list(pivot.GRAINS), index=2)
        where = cc[2].selectbox("Use as", ["Rows", "Columns"])
        if dcol:
            d, newcol = pivot.with_date_part(df, dcol, grain)
            if where == "Rows":
                rows = [newcol] + rows
            else:
                cols_ = [newcol] + cols_
            st.caption(f"Added **{newcol}** to {where}.")

if not rows:
    st.info("Pick at least one field for Rows.")
    st.stop()
if agg != "count" and not value:
    st.info("Pick a Value field for this aggregation (or use Count).")
    st.stop()
try:
    pv = pivot.build_pivot(d, rows, cols_ or None, value if agg != "count" else None, agg, show, margins, top or None)
except Exception as e:
    st.error(str(e))
    st.stop()

st.dataframe(pv.style.format("{:,.2f}" if show != "Value" or agg in ("mean", "median") else "{:,.0f}", na_rep=""))
st.download_button("Download pivot (Excel)", pivot.to_excel_bytes({"Pivot": pv}), f"{name}_pivot.xlsx")
if not cols_ and pv.shape[1] == 1:
    import plotly.express as px
    body = pv[pv.index != "Total"].reset_index()
    st.plotly_chart(px.bar(body, x=body.columns[-1], y=body.columns[0], orientation="h", title="Pivot chart") if len(rows) == 1 else
                    px.bar(body, x=body.columns[-1], y=body.iloc[:, 0].astype(str) + " / " + body.iloc[:, 1].astype(str), orientation="h"))
