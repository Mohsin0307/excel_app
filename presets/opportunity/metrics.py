"""
Saari dashboard metrics yahan hain (pandas). validate_sql.py inhi numbers ko SQL se dobara check karta hai.

Definitions (stakeholders ke liye):
  Sign-up            = applications table ki ek row (duplicates hatane ke baad)
  Completion rate    = completed sign-ups / total sign-ups
  "Last 7 dates"     = data ki aakhri 7 distinct dates jin par activity thi
  "Last 6 months"    = data ke sab se naye mahine se 6 mahine peeche tak (naya mahina adhoora ho sakta hai)
  Quarter change     = (naya quarter - purana quarter) / purana quarter * 100
  Scholarship opp    = microscholarship column khali / 0 / false / no / none na ho
"""
import numpy as np
import pandas as pd

from . import config as cfg


# ----------------------------------------------------------------------
# availability checks
# ----------------------------------------------------------------------
def has_apps(apps):
    return apps is not None and len(apps) > 0


def has_app_source(apps):
    return has_apps(apps) and bool((apps.app_lead_source != "Unknown").any())


def has_opp_source(opps):
    return bool((opps.opp_lead_source != "Unknown").any())


def completion_available(apps):
    return has_apps(apps) and bool(apps.app_completed.any())


def _not_archived(opps):
    return ~opps.opp_archived.fillna(False).astype(bool)


# ----------------------------------------------------------------------
# filters
# ----------------------------------------------------------------------
def apply_filters(opps, apps, categories=None, archived="All", sources=None, date_range=None):
    o = opps
    if categories:
        o = o[o.opp_category.isin(categories)]
    if archived == "Active only":
        o = o[_not_archived(o)]
    elif archived == "Archived only":
        o = o[~_not_archived(o)]

    a = apps
    start = end = None
    if date_range:
        start, end = pd.Timestamp(date_range[0]), pd.Timestamp(date_range[1])

    if has_apps(a):
        a = a[a.app_opp_id.isin(o.opp_id)]
        if sources and has_app_source(a):
            a = a[a.app_lead_source.isin(sources)]
        if start is not None:
            a = a[(a.app_date >= start) & (a.app_date <= end)]
    else:
        if sources and has_opp_source(o):
            o = o[o.opp_lead_source.isin(sources)]
        if start is not None:
            o = o[(o.opp_created >= start) & (o.opp_created <= end)]
    return o.copy(), (a.copy() if a is not None else None)


def events(opps, apps):
    """Trend charts kis cheez ko gintay: applications (agar hain) warna opportunities created."""
    if has_apps(apps):
        return apps[["app_date"]].rename(columns={"app_date": "date"}), "Applications"
    return opps[["opp_created"]].rename(columns={"opp_created": "date"}), "Opportunities created"


# ----------------------------------------------------------------------
# KPIs and per-opportunity performance
# ----------------------------------------------------------------------
def kpis(opps, apps):
    n = len(opps)
    k = {
        "total_opportunities": n,
        "active_opportunities": int(_not_archived(opps).sum()),
        "scholarship_opportunities": int(opps.has_scholarship.sum()),
        "avg_reward": float(opps.reward_num.mean()) if opps.reward_num.notna().any() else np.nan,
    }
    k["scholarship_share"] = k["scholarship_opportunities"] / n if n else np.nan
    if has_apps(apps):
        k["total_signups"] = len(apps)
        k["completed"] = int(apps.app_completed.sum())
        k["completion_rate"] = k["completed"] / len(apps)
    return k


def opportunity_performance(opps, apps):
    p = opps[["opp_id", "opp_name", "opp_category"]].copy()
    if has_apps(apps):
        g = apps.groupby("app_opp_id").agg(signups=("app_completed", "size"),
                                           completed=("app_completed", "sum"))
        p = p.merge(g, left_on="opp_id", right_index=True, how="left")
    else:
        p["signups"] = 0
        p["completed"] = 0
    p[["signups", "completed"]] = p[["signups", "completed"]].fillna(0).astype(int)
    p["completion_rate"] = p.completed / p.signups.where(p.signups > 0)
    name = p.opp_name.astype("object").where(p.opp_name.notna(), "Opportunity")
    p["label"] = name.astype(str).str.slice(0, 45) + " [" + p.opp_id.astype(str) + "]"
    return p


def signup_rank(perf, n):
    top = perf.sort_values(["signups", "opp_id"], ascending=[False, True]).head(n)
    low = perf[perf.signups >= 1].sort_values(["signups", "opp_id"]).head(n)
    return top, low


def completion_rank(perf, n, min_signups):
    e = perf[perf.signups >= min_signups]
    top = e.sort_values(["completion_rate", "signups", "opp_id"], ascending=[False, False, True]).head(n)
    low = e.sort_values(["completion_rate", "signups", "opp_id"], ascending=[True, False, True]).head(n)
    return top, low


def reward_rank(opps, n):
    d = opps[opps.reward_num.notna()].copy()
    d["label"] = d.opp_name.astype("object").where(d.opp_name.notna(), "Opportunity").astype(str).str.slice(0, 45) \
        + " [" + d.opp_id.astype(str) + "]"
    top = d.sort_values(["reward_num", "opp_id"], ascending=[False, True]).head(n)
    low = d.sort_values(["reward_num", "opp_id"]).head(n)
    return top, low


# ----------------------------------------------------------------------
# scholarship + lead source
# ----------------------------------------------------------------------
def scholarship_by_category(opps):
    g = opps.groupby("opp_category").agg(opportunities=("opp_id", "size"),
                                         with_scholarship=("has_scholarship", "sum")).reset_index()
    g["with_scholarship"] = g.with_scholarship.astype(int)
    g["scholarship_share_pct"] = (g.with_scholarship / g.opportunities * 100).round(1)
    return g.sort_values(["with_scholarship", "opp_category"], ascending=[False, True])


def opportunities_by_lead_source(opps, apps):
    if has_opp_source(opps):
        t = opps.groupby("opp_lead_source").size().reset_index()
        basis = "Each opportunity's own lead source."
    elif has_app_source(apps):
        t = apps.groupby("app_lead_source")["app_opp_id"].nunique().reset_index()
        basis = ("Distinct opportunities that received applications from each source "
                 "(one opportunity can appear under several sources).")
    else:
        return None, ""
    t.columns = ["lead_source", "opportunities"]
    return t.sort_values("opportunities", ascending=False), basis


def top_other(df, label, value, n=10):
    """Bohat saari categories ko top-n + 'Other' mein samet do (pie chart padhne layak rahe)."""
    if len(df) <= n:
        return df
    d = df.sort_values(value, ascending=False)
    other = pd.DataFrame({label: ["Other"], value: [d.iloc[n:][value].sum()]})
    return pd.concat([d.head(n), other], ignore_index=True)


def lead_source_performance(apps):
    if not has_app_source(apps):
        return None
    g = apps.groupby("app_lead_source").agg(applications=("app_completed", "size"),
                                            completed=("app_completed", "sum"),
                                            opportunities=("app_opp_id", "nunique")).reset_index()
    g = g.rename(columns={"app_lead_source": "lead_source"})
    g["completed"] = g.completed.astype(int)
    g["completion_rate"] = g.completed / g.applications
    g["share_pct"] = (g.applications / g.applications.sum() * 100).round(1)
    return g.sort_values("applications", ascending=False)


# ----------------------------------------------------------------------
# trends
# ----------------------------------------------------------------------
def last_n_dates(ev, n=7):
    d = ev.date.dropna()
    t = d.value_counts().sort_index().tail(n)
    return pd.DataFrame({"date": t.index.strftime("%Y-%m-%d"), "count": t.values})


def last_n_months(ev, n=6):
    d = ev.date.dropna()
    if d.empty:
        return pd.DataFrame({"month": [], "count": []})
    months = d.dt.to_period("M")
    idx = pd.period_range(end=months.max(), periods=n, freq="M")
    t = months.value_counts().reindex(idx, fill_value=0).sort_index()
    return pd.DataFrame({"month": idx.astype(str), "count": t.values})


def quarter_bounds(q):
    p = pd.Period(q, "Q")
    return p.start_time.strftime("%Y-%m-%d"), p.end_time.strftime("%Y-%m-%d")


def quarter_compare(opps, apps, a=None, b=None):
    a, b = a or cfg.COMPARE_FROM, b or cfg.COMPARE_TO
    pa, pb = pd.Period(a, "Q"), pd.Period(b, "Q")

    def cnt(s, p):
        return int((s.dt.to_period("Q") == p).sum())

    def pct(x, y):
        return round((y - x) / x * 100, 2) if x else np.nan

    rows = []
    if has_apps(apps):
        xa, xb = cnt(apps.app_date, pa), cnt(apps.app_date, pb)
        rows.append(("Applications", xa, xb, pct(xa, xb), "% change"))
        if completion_available(apps):
            c = apps[apps.app_completed]
            ca, cb = cnt(c.app_date, pa), cnt(c.app_date, pb)
            rows.append(("Completions", ca, cb, pct(ca, cb), "% change"))
            ra = ca / xa * 100 if xa else np.nan
            rb = cb / xb * 100 if xb else np.nan
            rows.append(("Completion rate (%)", round(ra, 2), round(rb, 2), round(rb - ra, 2), "pp change"))
    oa, ob = cnt(opps.opp_created, pa), cnt(opps.opp_created, pb)
    rows.append(("New opportunities", oa, ob, pct(oa, ob), "% change"))
    return pd.DataFrame(rows, columns=["metric", a, b, "change", "unit"])


# ----------------------------------------------------------------------
# insights (rule-based draft; final wording insaan ko review karni chahiye)
# ----------------------------------------------------------------------
def build_insights(opps, apps, min_signups=None, n=None, qa=None, qb=None):
    min_signups = min_signups or cfg.MIN_SIGNUPS_FOR_RATE
    n = n or cfg.TOP_N
    perf = opportunity_performance(opps, apps)
    out = []

    def add(finding, action=None):
        out.append((finding, action))

    if has_apps(apps) and perf.signups.sum() > 0:
        total = perf.signups.sum()
        top, low = signup_rank(perf, n)
        best = top.iloc[0]
        top_share = top.signups.sum() / total * 100
        add(f"**{best.label}** has the most sign-ups ({best.signups:,}, {best.signups / total * 100:.1f}% of all). "
            f"The top {n} opportunities bring {top_share:.1f}% of all sign-ups.",
            "Sign-ups are concentrated: copy the title, timing and promotion pattern of the top performers."
            if top_share >= 50 else None)
        zero = int((perf.signups == 0).sum())
        zs = zero / len(perf) * 100
        add(f"{zero:,} of {len(perf):,} opportunities ({zs:.1f}%) have zero sign-ups.",
            "Review these: promote, rewrite the description, or archive them." if zs >= 10 else None)

        if completion_available(apps):
            top_c, low_c = completion_rank(perf, 1, min_signups)
            overall = apps.app_completed.mean() * 100
            if len(top_c):
                add(f"Overall completion rate is {overall:.1f}%. Among opportunities with at least {min_signups} sign-ups, "
                    f"the best is **{top_c.iloc[0].label}** ({top_c.iloc[0].completion_rate * 100:.1f}%) and the weakest is "
                    f"**{low_c.iloc[0].label}** ({low_c.iloc[0].completion_rate * 100:.1f}%).",
                    "Investigate the weakest ones: duration, difficulty, fee, reminders and drop-off point.")

        lp_all = lead_source_performance(apps)
        lp = lp_all[lp_all.lead_source != "Unknown"] if lp_all is not None else None
        if lp is not None and len(lp):
            unk = lp_all[lp_all.lead_source == "Unknown"].share_pct.sum()
            big = lp.iloc[0]
            msg = f"**{big.lead_source}** is the largest known lead source ({big.applications:,} applications, {big.share_pct:.1f}% of all)."
            act = None
            if unk >= 20:
                msg += f" {unk:.1f}% of applications have no lead source recorded."
                act = "Make 'how did you hear about us' mandatory so channel performance can be measured reliably."
            if completion_available(apps):
                el = lp[lp.applications >= min_signups]
                if len(el):
                    bc = el.sort_values("completion_rate", ascending=False).iloc[0]
                    msg += f" Best completion rate: **{bc.lead_source}** ({bc.completion_rate * 100:.1f}%)."
                    if bc.lead_source != big.lead_source and act is None:
                        act = f"Volume and quality come from different sources: shift some effort toward {bc.lead_source}."
            add(msg, act)

    ev, basis = events(opps, apps)
    l7 = last_n_dates(ev, 7)
    if len(l7):
        hi, lo = l7.loc[l7["count"].idxmax()], l7.loc[l7["count"].idxmin()]
        add(f"{basis} over the last {len(l7)} active dates: busiest {hi.date} ({hi['count']:,}), quietest {lo.date} ({lo['count']:,}).")

    qa, qb = qa or cfg.COMPARE_FROM, qb or cfg.COMPARE_TO
    qc = quarter_compare(opps, apps, qa, qb)
    first = qc.iloc[0]
    ch = first["change"]
    if pd.notna(ch):
        word = "grew" if ch > 0 else "fell" if ch < 0 else "was flat"
        add(f"{first['metric']} {word} {abs(ch):.1f}% from {qa} to {qb} "
            f"({first[qa]:,.0f} -> {first[qb]:,.0f}).",
            "Find what drove the drop (channels, seasonality, fewer new opportunities) before planning the next quarter."
            if ch < -10 else None)

    both = opps[["opp_id", "reward_num"]].merge(perf[["opp_id", "signups"]], on="opp_id").dropna()
    if has_apps(apps) and len(both) >= 10 and both.reward_num.nunique() > 1:
        r = both.reward_num.corr(both.signups, method="spearman")
        if pd.notna(r):
            strength = "strong" if abs(r) >= 0.5 else "weak" if abs(r) < 0.2 else "moderate"
            add(f"Reward and sign-ups show a {strength} relationship (Spearman r = {r:.2f}).",
                "Reward alone does not drive sign-ups; test other levers." if abs(r) < 0.2 else None)

    sch = scholarship_by_category(opps)
    if len(sch) and sch.with_scholarship.sum() > 0:
        t = sch.iloc[0]
        add(f"{int(opps.has_scholarship.sum()):,} opportunities ({opps.has_scholarship.mean() * 100:.1f}%) include a scholarship; "
            f"**{t.opp_category}** has the most ({t.with_scholarship}).")
        if has_apps(apps):
            m = perf.merge(opps[["opp_id", "has_scholarship"]], on="opp_id").groupby("has_scholarship").signups.mean()
            if True in m.index and False in m.index:
                add(f"Average sign-ups: {m[True]:.1f} with scholarship vs {m[False]:.1f} without.",
                    "Scholarships coincide with higher demand: consider adding them where sign-ups lag."
                    if m[True] > m[False] * 1.2 else None)
    return out


def insights_markdown(opps, apps, **kw):
    lines = ["# Insights and recommendations (auto-generated draft)\n"]
    for f, a in build_insights(opps, apps, **kw):
        lines.append(f"- {f}")
        if a:
            lines.append(f"  - **Action:** {a}")
    return "\n".join(lines) + "\n"
