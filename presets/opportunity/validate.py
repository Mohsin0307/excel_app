"""
SQL validation: har KPI ko SQLite par SQL se dobara nikaal kar pandas wale number se compare karta hai.

    from presets.opportunity.validate import run
    report_df, sql_text = run(opps, apps)

CLI (data/ folder ki files par):  python scripts/run_opportunity_validation.py
SQL standard hai; Postgres/MySQL par sirf date functions (strftime/date) badalne honge.
"""
import sqlite3

import numpy as np
import pandas as pd

from . import config as cfg
from . import data_prep as dp
from . import metrics as m


def to_sql_frame(df):
    df = df.copy()
    for c in df.columns:
        if str(df[c].dtype).startswith("datetime"):
            df[c] = df[c].dt.strftime("%Y-%m-%d")
        elif str(df[c].dtype) == "boolean":
            df[c] = df[c].astype("Int64")
        elif df[c].dtype == bool:
            df[c] = df[c].astype(int)
    return df.astype(object).where(df.notna(), None)


def norm(v):
    if isinstance(v, dict):
        return {k: norm(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [norm(x) for x in v]
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return None
    if isinstance(v, (int, float, np.integer, np.floating)):
        return round(float(v), 6)
    return v


def same(a, b):
    a, b = norm(a), norm(b)
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(same(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(same(x, y) for x, y in zip(a, b))
    return a == b


def run(opps, apps, qa=None, qb=None, top_n=None, min_signups=None):
    HAS_APPS = m.has_apps(apps)
    HAS_DONE = m.completion_available(apps)
    con = sqlite3.connect(":memory:")
    to_sql_frame(opps[["opp_id", "opp_name", "opp_category", "opp_created", "opp_archived", "reward_raw",
                       "reward_num", "scholarship_raw", "opp_lead_source"]]).to_sql("opportunities", con, index=False)
    if HAS_APPS:
        to_sql_frame(apps[["app_id", "app_opp_id", "app_date", "app_lead_source", "app_completed"]]) \
            .to_sql("applications", con, index=False)
    results, sql_log = [], []

    def check(name, sql, dashboard_value, post=lambda r: r[0][0], params=()):
        rows = con.execute(sql, params).fetchall()
        sql_value = post(rows)
        ok = same(dashboard_value, sql_value)
        results.append({"metric": name, "dashboard_value": str(norm(dashboard_value))[:200],
                        "sql_value": str(norm(sql_value))[:200], "status": "PASS" if ok else "FAIL"})
        shown = sql
        for k_, v_ in (params if isinstance(params, dict) else {}).items():
            shown = shown.replace(f":{k_}", repr(v_))
        sql_log.append(f"-- {name}\n{shown.strip()};\n")

    N = top_n or cfg.TOP_N
    MIN = min_signups or cfg.MIN_SIGNUPS_FOR_RATE
    NO_SCH = ",".join(f"'{x}'" for x in sorted(dp.NO_SCHOLARSHIP))
    SCH_COND = f"scholarship_raw IS NOT NULL AND LOWER(TRIM(scholarship_raw)) NOT IN ({NO_SCH})"
    k = m.kpis(opps, apps)
    perf = m.opportunity_performance(opps, apps)

    # ----------------------------------------------------------------------
    # 1. Opportunity-level KPIs
    # ----------------------------------------------------------------------
    check("Total opportunities", "SELECT COUNT(DISTINCT opp_id) FROM opportunities", k["total_opportunities"])
    check("Active (not archived) opportunities",
          "SELECT COUNT(*) FROM opportunities WHERE COALESCE(opp_archived, 0) = 0", k["active_opportunities"])
    check("Opportunities with scholarship",
          f"SELECT COUNT(*) FROM opportunities WHERE {SCH_COND}", k["scholarship_opportunities"])

    sch = m.scholarship_by_category(opps)
    check("Scholarship opportunities by category",
          f"SELECT opp_category, SUM(CASE WHEN {SCH_COND} THEN 1 ELSE 0 END) FROM opportunities GROUP BY opp_category",
          dict(zip(sch.opp_category, sch.with_scholarship)), post=lambda r: {a: b for a, b in r})

    if opps.reward_num.notna().any():
        check("Average reward", "SELECT AVG(reward_num) FROM opportunities", k["avg_reward"])
        top_r, low_r = m.reward_rank(opps, N)
        check(f"Top {N} reward values",
              f"SELECT reward_num FROM opportunities WHERE reward_num IS NOT NULL ORDER BY reward_num DESC, opp_id LIMIT {N}",
              list(top_r.reward_num), post=lambda r: [x[0] for x in r])
        check(f"Lowest {N} reward values",
              f"SELECT reward_num FROM opportunities WHERE reward_num IS NOT NULL ORDER BY reward_num ASC, opp_id LIMIT {N}",
              list(low_r.reward_num), post=lambda r: [x[0] for x in r])

    # ----------------------------------------------------------------------
    # 2. Sign-up and completion (needs applications)
    # ----------------------------------------------------------------------
    if HAS_APPS:
        check("Total sign-ups (applications)", "SELECT COUNT(*) FROM applications", k["total_signups"])
        top_s, low_s = m.signup_rank(perf, N)
        check(f"Top {N} opportunities by sign-ups (counts)",
              f"""SELECT COUNT(a.app_opp_id) AS signups FROM opportunities o
    LEFT JOIN applications a ON a.app_opp_id = o.opp_id
    GROUP BY o.opp_id ORDER BY signups DESC, o.opp_id LIMIT {N}""",
              list(top_s.signups), post=lambda r: [x[0] for x in r])
        check(f"Lowest {N} opportunities by sign-ups (counts, min 1 sign-up)",
              f"""SELECT COUNT(*) AS signups FROM applications
    GROUP BY app_opp_id ORDER BY signups ASC, app_opp_id LIMIT {N}""",
              list(low_s.signups), post=lambda r: [x[0] for x in r])
        check("Opportunities with zero sign-ups",
              """SELECT COUNT(*) FROM opportunities o
    WHERE NOT EXISTS (SELECT 1 FROM applications a WHERE a.app_opp_id = o.opp_id)""",
              int((perf.signups == 0).sum()))

        if HAS_DONE:
            check("Completed sign-ups", "SELECT SUM(app_completed) FROM applications", k["completed"])
            check("Overall completion rate", "SELECT 1.0 * SUM(app_completed) / COUNT(*) FROM applications",
                  k["completion_rate"])
            top_c, low_c = m.completion_rank(perf, N, MIN)
            base = """SELECT 1.0 * SUM(app_completed) / COUNT(*) AS rate FROM applications
    GROUP BY app_opp_id HAVING COUNT(*) >= :min ORDER BY rate {d}, COUNT(*) {s}, app_opp_id LIMIT %d""" % N
            check(f"Top {N} completion rates (min {MIN} sign-ups)", base.format(d="DESC", s="DESC"),
                  list(top_c.completion_rate), post=lambda r: [x[0] for x in r], params={"min": MIN})
            check(f"Lowest {N} completion rates (min {MIN} sign-ups)", base.format(d="ASC", s="DESC"),
                  list(low_c.completion_rate), post=lambda r: [x[0] for x in r], params={"min": MIN})

        # lead source
        lp = m.lead_source_performance(apps)
        if lp is not None:
            check("Applications by lead source",
                  "SELECT app_lead_source, COUNT(*) FROM applications GROUP BY app_lead_source",
                  dict(zip(lp.lead_source, lp.applications)), post=lambda r: {a: b for a, b in r})
            if HAS_DONE:
                check("Completion rate by lead source",
                      """SELECT app_lead_source, 1.0 * SUM(app_completed) / COUNT(*)
    FROM applications GROUP BY app_lead_source""",
                      dict(zip(lp.lead_source, lp.completion_rate)), post=lambda r: {a: b for a, b in r})

    # ----------------------------------------------------------------------
    # 3. Lead source of opportunities
    # ----------------------------------------------------------------------
    ls, _ = m.opportunities_by_lead_source(opps, apps)
    if ls is not None:
        if m.has_opp_source(opps):
            sql = "SELECT opp_lead_source, COUNT(*) FROM opportunities GROUP BY opp_lead_source"
        else:
            sql = "SELECT app_lead_source, COUNT(DISTINCT app_opp_id) FROM applications GROUP BY app_lead_source"
        check("Opportunities by lead source", sql, dict(zip(ls.lead_source, ls.opportunities)),
              post=lambda r: {a: b for a, b in r})

    # ----------------------------------------------------------------------
    # 4. Trends
    # ----------------------------------------------------------------------
    ev, basis = m.events(opps, apps)
    T, D = ("applications", "app_date") if HAS_APPS else ("opportunities", "opp_created")

    l7 = m.last_n_dates(ev, 7)
    check(f"{basis}: last 7 active dates",
          f"""SELECT {D}, COUNT(*) FROM {T} WHERE {D} IS NOT NULL
    GROUP BY {D} ORDER BY {D} DESC LIMIT 7""",
          dict(zip(l7.date, l7["count"])), post=lambda r: {a: b for a, b in r})

    l6 = m.last_n_months(ev, 6)
    if len(l6):
        check(f"{basis}: last 6 months",
              f"""SELECT strftime('%Y-%m', {D}) AS month, COUNT(*) FROM {T}
    WHERE {D} >= date((SELECT MAX({D}) FROM {T}), 'start of month', '-5 months')
    GROUP BY month ORDER BY month""",
              dict(zip(l6.month, l6["count"])),
              post=lambda r: {mo: dict(r).get(mo, 0) for mo in l6.month})

    qc = m.quarter_compare(opps, apps, qa or cfg.COMPARE_FROM, qb or cfg.COMPARE_TO)
    qa, qb = qa or cfg.COMPARE_FROM, qb or cfg.COMPARE_TO
    (a0, a1), (b0, b1) = m.quarter_bounds(qa), m.quarter_bounds(qb)


    def q_count(table, col, lo, hi, extra=""):
        return f"SELECT COUNT(*) FROM {table} WHERE {col} BETWEEN '{lo}' AND '{hi}' {extra}"


    first = qc.iloc[0]
    check(f"{first['metric']} {qa}", q_count(T, D, a0, a1), int(first[qa]))
    check(f"{first['metric']} {qb}", q_count(T, D, b0, b1), int(first[qb]))
    if pd.notna(first["change"]):
        check(f"{first['metric']} % change {qa} -> {qb}",
              f"""SELECT ROUND(100.0 * (
     (SELECT COUNT(*) FROM {T} WHERE {D} BETWEEN '{b0}' AND '{b1}') -
     (SELECT COUNT(*) FROM {T} WHERE {D} BETWEEN '{a0}' AND '{a1}')) /
     (SELECT COUNT(*) FROM {T} WHERE {D} BETWEEN '{a0}' AND '{a1}'), 2)""",
              float(first["change"]))
    if HAS_DONE:
        comp = qc[qc.metric == "Completions"].iloc[0]
        check(f"Completions {qa}", q_count("applications", "app_date", a0, a1, "AND app_completed = 1"), int(comp[qa]))
        check(f"Completions {qb}", q_count("applications", "app_date", b0, b1, "AND app_completed = 1"), int(comp[qb]))
    no = qc[qc.metric == "New opportunities"].iloc[0]
    check(f"New opportunities {qa}", q_count("opportunities", "opp_created", a0, a1), int(no[qa]))
    check(f"New opportunities {qb}", q_count("opportunities", "opp_created", b0, b1), int(no[qb]))

    con.close()
    return pd.DataFrame(results), "\n".join(sql_log)
