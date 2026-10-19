"""Opportunity dashboard view. Call render(OPPS, APPS, LOG) with the output of data_prep.load_all()."""
import pandas as pd
import plotly.express as px
import streamlit as st

from . import config as cfg
from . import data_prep as dp
from . import metrics as m
from . import validate


def render(OPPS, APPS, LOG):
    HAS_APPS = m.has_apps(APPS)

    # ----------------------------------------------------------------------
    # Sidebar filters
    # ----------------------------------------------------------------------
    st.sidebar.header("Filters")
    cats = st.sidebar.multiselect("Category (empty = all)", sorted(OPPS.opp_category.unique()))
    archived = st.sidebar.radio("Opportunity status", ["All", "Active only", "Archived only"])

    src_values = []
    if m.has_app_source(APPS):
        src_values = list(APPS.app_lead_source.value_counts().head(30).index)  # top 30 sources
    elif m.has_opp_source(OPPS):
        src_values = sorted(OPPS.opp_lead_source.unique())
    sources = st.sidebar.multiselect("Lead source (empty = all)", src_values) if src_values else None

    ev_all, basis = m.events(OPPS, APPS)
    dmin, dmax = ev_all.date.min(), ev_all.date.max()
    date_range = None
    if pd.notna(dmin):
        picked = st.sidebar.date_input(f"Date range ({basis.lower()})", (dmin.date(), dmax.date()),
                                       min_value=dmin.date(), max_value=dmax.date())
        if isinstance(picked, (list, tuple)) and len(picked) == 2:
            date_range = picked

    quarters = sorted(set(ev_all.date.dropna().dt.to_period("Q").astype(str)))
    if len(quarters) >= 2:
        QA = st.sidebar.selectbox("Compare from quarter", quarters,
                                  index=quarters.index(cfg.COMPARE_FROM) if cfg.COMPARE_FROM in quarters else len(quarters) - 2)
        QB = st.sidebar.selectbox("Compare to quarter", quarters,
                                  index=quarters.index(cfg.COMPARE_TO) if cfg.COMPARE_TO in quarters else len(quarters) - 1)
    else:
        QA, QB = cfg.COMPARE_FROM, cfg.COMPARE_TO
    top_n = st.sidebar.slider("Top / bottom N", 5, 20, cfg.TOP_N)
    min_signups = st.sidebar.slider("Min sign-ups for completion ranking", 1, 200, cfg.MIN_SIGNUPS_FOR_RATE)
    st.sidebar.caption("Trend charts (last 7 dates, last 6 months, quarter comparison) ignore the date-range filter "
                       "but respect the other filters.")

    O, A = m.apply_filters(OPPS, APPS, cats, archived, sources, date_range)        # KPIs, rankings
    Ot, At = m.apply_filters(OPPS, APPS, cats, archived, sources, None)            # trends

    # ----------------------------------------------------------------------
    # Header + KPIs
    # ----------------------------------------------------------------------
    st.title("Opportunity Performance Dashboard")
    if not HAS_APPS:
        st.info("Applications file not found in data/. Sign-up, completion and lead-source (applications) views are off. "
                "Add an applications/sign-ups file and map its columns in config.py to enable them.")
    if len(O) == 0:
        st.warning("No opportunities match the current filters.")
        st.stop()

    K = m.kpis(O, A)
    QC = m.quarter_compare(Ot, At, QA, QB)
    c = st.columns(6)
    c[0].metric("Opportunities", f"{K['total_opportunities']:,}", f"{K['active_opportunities']:,} active", delta_color="off")
    c[1].metric("Sign-ups", f"{K['total_signups']:,}" if HAS_APPS else "n/a")
    c[2].metric("Completion rate", f"{K['completion_rate'] * 100:.1f}%" if m.completion_available(A) else "n/a")
    c[3].metric("Avg reward", f"{K['avg_reward']:,.0f}" if pd.notna(K["avg_reward"]) else "n/a")
    c[4].metric("With scholarship", f"{K['scholarship_opportunities']:,}", f"{K['scholarship_share'] * 100:.1f}% of opps",
                delta_color="off")
    q0 = QC.iloc[0]
    c[5].metric(f"{q0['metric']}: {QB} vs {QA}",
                f"{int(q0[QB]):,}", f"{q0['change']:+.1f}%" if pd.notna(q0["change"]) else None)

    PERF = m.opportunity_performance(O, A)


    def hbar(df, x, y, title, color=None, fmt=None, ascending=True):
        fig = px.bar(df, x=x, y=y, orientation="h", title=title, text=x, color_discrete_sequence=[color or "#2E75B6"])
        if fmt:
            fig.update_traces(texttemplate=fmt)
        fig.update_layout(yaxis={"categoryorder": "total ascending" if ascending else "total descending"},
                          height=420, margin=dict(l=0, r=10, t=50, b=0), yaxis_title=None)
        return fig


    tabs = st.tabs(["Sign-ups & completion", "Rewards", "Trends", "Scholarships & lead sources",
                    "Insights", "Data quality & validation"])

    # ----------------------------------------------------------------------
    # Tab 1: sign-ups and completion
    # ----------------------------------------------------------------------
    with tabs[0]:
        if not HAS_APPS:
            st.info("Needs the applications file.")
        else:
            st.caption("Purpose: find which opportunities attract sign-ups and which convert sign-ups into completions.")
            top, low = m.signup_rank(PERF, top_n)
            a, b = st.columns(2)
            a.plotly_chart(hbar(top, "signups", "label", f"Top {top_n} by sign-ups"))
            b.plotly_chart(hbar(low, "signups", "label", f"Lowest {top_n} by sign-ups (at least 1 sign-up)",
                                color="#C0504D", ascending=False))
            st.caption(f"{int((PERF.signups == 0).sum()):,} opportunities have zero sign-ups (not shown in the lowest chart).")
            if m.completion_available(A):
                tc, lc = m.completion_rank(PERF, top_n, min_signups)
                tc, lc = tc.assign(rate=tc.completion_rate * 100), lc.assign(rate=lc.completion_rate * 100)
                a, b = st.columns(2)
                a.plotly_chart(hbar(tc, "rate", "label", f"Top {top_n} completion rate (%)", fmt="%{x:.1f}%"))
                b.plotly_chart(hbar(lc, "rate", "label", f"Lowest {top_n} completion rate (%)", color="#C0504D",
                                    fmt="%{x:.1f}%", ascending=False))
                st.caption(f"Only opportunities with at least {min_signups} sign-ups are ranked, so tiny samples don't distort rates.")
            else:
                st.info("No completion information found (set APP_COLS['status'] or ['completed'] in config.py).")

    # ----------------------------------------------------------------------
    # Tab 2: rewards
    # ----------------------------------------------------------------------
    with tabs[1]:
        st.caption("Purpose: see how rewards are spread and which opportunities offer the most / least.")
        if O.reward_num.notna().any():
            a, b = st.columns(2)
            fig = px.histogram(O.dropna(subset=["reward_num"]), x="reward_num", nbins=30, title="Reward distribution",
                               color_discrete_sequence=["#2E75B6"])
            fig.update_layout(height=380, xaxis_title="Reward", margin=dict(l=0, r=10, t=50, b=0))
            a.plotly_chart(fig)
            by_cat = O.groupby("opp_category").reward_num.mean().dropna().reset_index()
            b.plotly_chart(hbar(by_cat.round(0), "reward_num", "opp_category", "Average reward by category"))
            tr, lr = m.reward_rank(O, top_n)
            a, b = st.columns(2)
            a.plotly_chart(hbar(tr, "reward_num", "label", f"Highest {top_n} rewards"))
            b.plotly_chart(hbar(lr, "reward_num", "label", f"Lowest {top_n} rewards", color="#C0504D", ascending=False))
            st.caption("Reward value = first number found in the Reward column text. Check the 'Data quality' tab for samples.")
        elif O.reward_raw.notna().any():
            t = O.reward_raw.value_counts().head(10).reset_index()
            t.columns = ["reward", "opportunities"]
            st.plotly_chart(px.pie(t, names="reward", values="opportunities", hole=0.4, title="Reward types (top 10)"))
            st.info("Reward column has no numbers, so it is shown as categories.")
        else:
            st.info("Reward column is empty or not mapped (config.py OPP_COLS['reward']).")

    # ----------------------------------------------------------------------
    # Tab 3: trends
    # ----------------------------------------------------------------------
    with tabs[2]:
        st.caption(f"Purpose: track momentum. Counting: {basis.lower()}.")
        EV, _ = m.events(Ot, At)
        a, b = st.columns(2)
        l7 = m.last_n_dates(EV, 7)
        fig = px.bar(l7, x="date", y="count", text="count", title=f"{basis}: last 7 active dates",
                     color_discrete_sequence=["#2E75B6"])
        fig.update_xaxes(type="category")
        fig.update_layout(height=380, margin=dict(l=0, r=10, t=50, b=0))
        a.plotly_chart(fig)
        l6 = m.last_n_months(EV, 6)
        fig = px.line(l6, x="month", y="count", markers=True, text="count", title=f"{basis}: last 6 months")
        fig.update_traces(textposition="top center")
        fig.update_layout(height=380, margin=dict(l=0, r=10, t=50, b=0))
        b.plotly_chart(fig)
        st.caption("Last month may be partial. 'Last 7 dates' = the 7 most recent dates that have activity in the data.")

        st.subheader(f"{QA} vs {QB}")
        QC = m.quarter_compare(Ot, At, QA, QB)
        counts = QC[QC.unit == "% change"].melt(id_vars=["metric", "change", "unit"],
                                               value_vars=[QA, QB],
                                               var_name="quarter", value_name="value")
        a, b = st.columns([3, 2])
        fig = px.bar(counts, x="metric", y="value", color="quarter", barmode="group", text="value")
        fig.update_layout(height=360, margin=dict(l=0, r=10, t=20, b=0), xaxis_title=None)
        a.plotly_chart(fig)
        b.dataframe(QC.rename(columns={"unit": "change type"}), hide_index=True)

    # ----------------------------------------------------------------------
    # Tab 4: scholarships and lead sources
    # ----------------------------------------------------------------------
    with tabs[3]:
        st.caption("Purpose: where scholarships sit across categories, and which channels bring activity.")
        sch = m.scholarship_by_category(O)
        a, b = st.columns(2)
        if sch.with_scholarship.sum() > 0:
            a.plotly_chart(hbar(sch[sch.with_scholarship > 0], "with_scholarship", "opp_category",
                                "Scholarship opportunities by category"))
            b.plotly_chart(px.pie(sch[sch.with_scholarship > 0], names="opp_category", values="with_scholarship",
                                  hole=0.4, title="Share of scholarships by category"))
        else:
            st.info("No scholarship opportunities found (check OPP_COLS['scholarship'] in config.py).")
        st.dataframe(sch.rename(columns={"opp_category": "category"}), hide_index=True)

        ls, basis_txt = m.opportunities_by_lead_source(O, A)
        lp = m.lead_source_performance(A)
        if ls is None:
            st.info("No lead-source data found. Map it in config.py (OPP_COLS['lead_source'] or APP_COLS['lead_source']).")
        else:
            a, b = st.columns(2)
            a.plotly_chart(px.pie(m.top_other(ls, "lead_source", "opportunities", 10), names="lead_source",
                                  values="opportunities", hole=0.4, title="Opportunity distribution by lead source (top 10)"))
            a.caption(basis_txt)
            if lp is not None:
                b.plotly_chart(hbar(lp.head(15), "applications", "lead_source", "Applications by lead source (top 15)"))
                if m.completion_available(A):
                    lp2 = lp[lp.applications >= min_signups].assign(rate=lambda d: d.completion_rate * 100).head(15)
                    st.plotly_chart(hbar(lp2, "rate", "lead_source",
                                         f"Completion rate by lead source (%), sources with at least {min_signups} applications",
                                         fmt="%{x:.1f}%", color="#70AD47"))
                st.dataframe(lp, hide_index=True)

    # ----------------------------------------------------------------------
    # Tab 5: insights
    # ----------------------------------------------------------------------
    with tabs[4]:
        st.caption("Auto-generated from the filtered data. Treat as a first draft and add business context before presenting.")
        items = m.build_insights(O, A, min_signups, top_n, qa=QA, qb=QB)
        for f, act in items:
            st.markdown(f"- {f}")
            if act:
                st.markdown(f"  - **Action:** {act}")
        st.download_button("Download insights (.md)", m.insights_markdown(O, A, qa=QA, qb=QB), "insights.md")

    # ----------------------------------------------------------------------
    # Tab 6: data quality and validation
    # ----------------------------------------------------------------------
    with tabs[5]:
        st.subheader("Cleaning log")
        st.code("\n".join(LOG))
        st.subheader("Opportunities: missing values")
        st.dataframe(dp.quality_report(OPPS.drop(columns=[c for c in OPPS.columns
                                                          if c.startswith(("opp_", "reward_", "scholarship_", "has_"))])),
                     hide_index=True)
        st.subheader("Reward parsing sample (raw text -> number used)")
        st.dataframe(OPPS[["reward_raw", "reward_num"]].dropna(subset=["reward_raw"]).drop_duplicates("reward_raw").head(15),
                     hide_index=True)
        st.subheader("SQL validation")
        st.caption("Re-computes every KPI with SQL on the full cleaned data (no filters) and compares it with the dashboard code.")
        if st.button("Run SQL validation"):
            with st.spinner("Running SQL checks..."):
                st.session_state["opp_validation"] = validate.run(OPPS, APPS, QA, QB, top_n, min_signups)
        if "opp_validation" in st.session_state:
            v, sql_text = st.session_state["opp_validation"]
            st.write(f"**{(v.status == 'PASS').sum()}/{len(v)} checks passed**")
            st.dataframe(v, hide_index=True)
            st.download_button("Download validation report (CSV)", v.to_csv(index=False), "validation_report.csv")
            st.download_button("Download SQL queries (.sql)", sql_text, "validation_queries.sql")
        st.download_button("Download cleaned opportunities (CSV)",
                           OPPS.to_csv(index=False).encode("utf-8-sig"), "cleaned_opportunities.csv")
