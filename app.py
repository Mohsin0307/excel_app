"""Data Insight Studio: Home / upload.   Run:  streamlit run app.py"""
import streamlit as st

from core import sample, state, ui

st.set_page_config(page_title="Data Insight Studio", page_icon="📊", layout="wide")
st.title("📊 Data Insight Studio")
st.caption("Upload an Excel or CSV file. The app cleans it, detects column types, and builds KPIs, charts, pivot tables, "
           "measures and pattern insights automatically.")

with st.expander("Cleaning options", expanded=False):
    c = st.columns(5)
    opts = dict(drop_duplicates=c[0].checkbox("Remove duplicate rows", True),
                parse_numbers=c[1].checkbox("Text -> numbers", True),
                parse_dates=c[2].checkbox("Text -> dates", True),
                strip_html=c[3].checkbox("Strip HTML", True),
                dayfirst=c[4].checkbox("Dates are day-first (31/12/2025)", False))

files = st.file_uploader("Upload Excel / CSV (multiple files and multi-sheet workbooks are supported)",
                         type=["xlsx", "xlsm", "xls", "csv"], accept_multiple_files=True)
done = st.session_state.setdefault("processed", set())
for f in files or []:
    key = (f.name, f.size)
    if key in done:
        continue
    try:
        with st.spinner(f"Reading {f.name}..."):
            names = state.add_file(f.name, f.getvalue(), opts)
        done.add(key)
        st.success(f"{f.name}: loaded {len(names)} table(s)")
    except Exception as e:
        st.error(f"{f.name}: {e}")

st.markdown("**No file handy?**")
b = st.columns(4)
if b[0].button("Load sales sample"):
    state.add_frame("sales_demo", sample.sales_demo(), opts)
if b[1].button("Load opportunity sample (2 tables)"):
    o, a = sample.opportunity_demo()
    state.add_frame("opportunities_demo", o, opts)
    state.add_frame("applications_demo", a, opts)

datasets = state.store()
if not datasets:
    st.info("Upload a file above to begin.")
    st.stop()

st.subheader("Loaded tables")
for name, d in list(datasets.items()):
    df = d["clean"]
    c = st.columns([5, 1])
    c[0].markdown(f"**{name}**: {len(df):,} rows x {df.shape[1]} columns (raw: {len(d['raw']):,} rows)")
    if c[1].button("Remove", key=f"rm_{name}"):
        state.remove(name)
        st.rerun()
    with st.expander(f"Cleaning log and preview: {name}"):
        st.code("\n".join(d["log"]))
        st.dataframe(df.head(100), hide_index=True)

st.success("Next: open **Overview** in the left sidebar. Pick the active table there if you loaded several.")
