import pandas as pd
import streamlit as st

from core import analysis as an
from core import detector as dt
from core import pivot, ui

name, df, prof = ui.setup("Overview", "🧭")
df = ui.sidebar_filters(df, prof)

st.caption(f"Table: **{name}**. Column types are auto-detected; check the schema below and tell me if any look wrong.")
cards = an.kpi_cards(df, prof)
for i in range(0, len(cards), 4):
    cols = st.columns(4)
    for col, k in zip(cols, cards[i:i + 4]):
        col.metric(k["label"], k["value"], k.get("delta"), delta_color=k.get("delta_color", "normal"), help=k.get("help"))

t1, t2, t3 = st.tabs(["Auto insights", "Schema (detected)", "Data quality"])
with t1:
    ins = pd.DataFrame(an.generate_insights(df, prof))
    if ins.empty:
        st.info("No notable patterns found.")
    else:
        for kind, label in [("trend", "Trends"), ("pattern", "Patterns"), ("quality", "Data quality")]:
            sub = ins[ins.type == kind]
            if len(sub):
                st.markdown(f"**{label}**")
                for t in sub.insight:
                    st.markdown(f"- {t}")
        st.caption("Rule-based findings. Verify against business context before acting on them.")
with t2:
    st.write("Roles: " + ", ".join(f"{k}: {v}" for k, v in dt.schema_summary(prof).items()))
    st.dataframe(prof.drop(columns=["unique_pct"]), hide_index=True)
    st.caption(f"Primary date: **{dt.primary_date(df, prof)}**; primary ID: **{dt.primary_id(prof)}**")
with t3:
    miss = prof[["column", "role", "missing_pct", "unique"]].sort_values("missing_pct", ascending=False)
    st.dataframe(miss, hide_index=True)
    out = an.outlier_summary(df, dt.measures(prof))
    if len(out):
        st.markdown("**Outliers (IQR rule)**")
        st.dataframe(out, hide_index=True)

report = pivot.to_excel_bytes({"schema": prof, "insights": pd.DataFrame(an.generate_insights(df, prof)),
                               "kpis": pd.DataFrame(cards)})
st.download_button("Download analysis report (Excel)", report, f"{name}_analysis.xlsx")
