"""Preset: the opportunity / applications dashboard built earlier, now fed from uploaded tables."""
import pandas as pd
import streamlit as st

from core import state, ui
from presets.opportunity import config as ocfg
from presets.opportunity import data_prep as dp
from presets.opportunity import view

name, _, _ = ui.setup("Opportunity Dashboard", "🎯", need_data=False)
store = state.store()
if not store:
    st.info("Upload your **opportunities** Excel (and the **applications** Excel) on **Home**, or load the opportunity sample there.")
    st.stop()


def guess(kind):
    best, score = None, -1
    for n, d in store.items():
        cols = {str(c).lower() for c in d["raw"].columns}
        if kind == "opps":
            s = len(cols & {"opportunity_id", "short_description", "long_description", "microscholarship", "reward", "is_archived"})
        else:
            s = len(cols & {"application_id", "apply_date", "completion_date", "work_item_sk", "relation_id", "status", "withdraw_date"})
        if s > score:
            best, score = n, s
    return best


names = list(store)
c = st.columns(2)
opp_name = c[0].selectbox("Opportunities table", names, index=names.index(guess("opps")))
app_opts = ["(none)"] + names
app_name = c[1].selectbox("Applications / sign-ups table (optional)", app_opts,
                          index=app_opts.index(guess("apps")) if guess("apps") != opp_name else 0)

with st.expander("Column mapping (change only if auto-detection is wrong)"):
    oc, ac = {}, {}
    st.markdown("**Opportunities table**")
    cc = st.columns(4)
    for i, (k, v) in enumerate(ocfg.OPP_COLS.items()):
        oc[k] = cc[i % 4].text_input(k, v or "", key=f"o_{k}") or None
    st.markdown("**Applications table** (separate several columns with commas; `auto` finds the opportunity link by itself)")
    cc = st.columns(4)
    for i, (k, v) in enumerate(ocfg.APP_COLS.items()):
        raw = ", ".join(v) if isinstance(v, list) else (v or "")
        txt = cc[i % 4].text_input(k, raw, key=f"a_{k}")
        parts = [p.strip() for p in txt.split(",") if p.strip()]
        ac[k] = None if not parts else parts if k in ("date", "lead_source") else parts[0]


@st.cache_data(show_spinner="Cleaning and joining tables...", max_entries=3)
def load(opp_df, app_df, oc, ac):
    with ocfg.override(oc, ac):
        return dp.load_all(opp_df, app_df)


try:
    d = load(store[opp_name]["raw"], store[app_name]["raw"] if app_name != "(none)" else None, oc, ac)
except (ValueError, KeyError) as e:
    st.error(f"Could not build the dashboard: {e}")
    st.stop()
st.divider()
view.render(d["opps"], d["apps"], d["log"])
