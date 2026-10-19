"""Common page setup: page config, dataset picker, shared sidebar filters."""
import pandas as pd
import streamlit as st

from . import detector as dt
from . import state


def setup(title, icon="📊", need_data=True):
    st.set_page_config(page_title=f"{title} | Data Insight Studio", page_icon=icon, layout="wide")
    s = state.store()
    if s:
        names = list(s)
        cur = st.session_state.get("active")
        st.sidebar.selectbox("Active table", names, index=names.index(cur) if cur in names else 0, key="active")
    st.title(f"{icon} {title}")
    name, df, prof = state.active()
    if need_data and df is None:
        st.info("No data yet. Go to **Home** (left sidebar) and upload an Excel/CSV file, or load the sample data.")
        st.stop()
    return name, df, prof


def sidebar_filters(df, prof, key="f"):
    """Date range + upto 4 category filters. Returns filtered df."""
    out = df
    with st.sidebar.expander("Filters", expanded=False):
        pdate = dt.primary_date(df, prof)
        if pdate and df[pdate].notna().any():
            lo, hi = df[pdate].min().date(), df[pdate].max().date()
            r = st.date_input(f"{pdate}", (lo, hi), min_value=lo, max_value=hi, key=f"{key}_date")
            if isinstance(r, (list, tuple)) and len(r) == 2:
                out = out[(out[pdate] >= pd.Timestamp(r[0])) & (out[pdate] < pd.Timestamp(r[1]) + pd.Timedelta(days=1))]
        for d in dt.dimensions(prof, 30)[:4]:
            vals = sorted(df[d].dropna().astype(str).unique())
            pick = st.multiselect(d, vals, key=f"{key}_{d}")
            if pick:
                out = out[out[d].astype(str).isin(pick)]
        st.caption(f"{len(out):,} of {len(df):,} rows selected")
    return out
