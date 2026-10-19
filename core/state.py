"""Session state: uploaded tables ek jagah rakhna, taake saare pages unhe use karein."""
import streamlit as st

from . import cleaner, detector, loader


def store():
    return st.session_state.setdefault("datasets", {})   # name -> {"raw", "clean", "log"}


def add_file(name, data, opts):
    """File parse + clean karke store karo. Returns list of table names."""
    added = []
    for tname, raw in loader.read_file(name, data).items():
        clean, log = cleaner.clean(raw, **opts)
        store()[tname] = {"raw": raw, "clean": clean, "log": log}
        added.append(tname)
    if added and "active" not in st.session_state:
        st.session_state["active"] = added[0]
    return added


def add_frame(name, raw, opts):
    clean, log = cleaner.clean(raw, **opts)
    store()[name] = {"raw": raw, "clean": clean, "log": log}
    st.session_state["active"] = name


def remove(name):
    store().pop(name, None)
    if st.session_state.get("active") == name:
        st.session_state["active"] = next(iter(store()), None)


@st.cache_data(show_spinner=False, max_entries=8)
def profile(df):
    return detector.detect_roles(df)


def active():
    """(name, clean_df, profile) ya (None, None, None)."""
    s = store()
    name = st.session_state.get("active")
    if not s or name not in s:
        return None, None, None
    df = s[name]["clean"]
    return name, df, profile(df)
