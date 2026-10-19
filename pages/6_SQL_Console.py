import sqlite3

import pandas as pd
import streamlit as st

from core import pivot, state, ui

name, df, prof = ui.setup("SQL Console", "🗄️")
st.caption("Run SQL (SQLite) on your uploaded tables. Use it to double-check any number in the app.")

tables = {}
for n, d in state.store().items():
    t = "".join(ch if ch.isalnum() else "_" for ch in n).strip("_").lower()
    tables[t if not t[0].isdigit() else f"t_{t}"] = d["clean"]


con = sqlite3.connect(":memory:", check_same_thread=False)
for t, d in tables.items():
    x = d.copy()
    for c in x.columns:
        if str(x[c].dtype).startswith("datetime"):
            x[c] = x[c].dt.strftime("%Y-%m-%d %H:%M:%S")
        elif str(x[c].dtype) == "boolean":
            x[c] = x[c].astype("Int64")
    x.astype(object).where(x.notna(), None).to_sql(t, con, index=False)

st.write("Tables: " + ", ".join(f"`{t}` ({len(d):,} rows)" for t, d in tables.items()))
with st.expander("Columns"):
    for t, d in tables.items():
        st.markdown(f"`{t}`: " + ", ".join(f"`{c}`" for c in d.columns))
first = next(iter(tables))
q = st.text_area("SQL", f'SELECT COUNT(*) AS total_rows FROM "{first}"', height=140)
if st.button("Run query"):
    try:
        res = pd.read_sql_query(q, con)
        st.write(f"{len(res):,} rows")
        st.dataframe(res.head(5000), hide_index=True)
        st.download_button("Download result (Excel)", pivot.to_excel_bytes({"result": res.head(100000)}), "query_result.xlsx")
    except Exception as e:
        st.error(str(e))
