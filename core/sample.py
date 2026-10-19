"""Demo data: koi file na ho to app try karne ke liye."""
import numpy as np
import pandas as pd


def sales_demo(n=3000, seed=1):
    rng = np.random.default_rng(seed)
    dates = pd.to_datetime(rng.choice(pd.date_range("2025-01-01", "2026-06-30"), n))
    region = rng.choice(["North", "South", "East", "West"], n, p=[.35, .25, .25, .15])
    product = rng.choice(["Laptop", "Phone", "Tablet", "Monitor", "Keyboard"], n, p=[.15, .3, .15, .2, .2])
    price = pd.Series(product).map({"Laptop": 900, "Phone": 600, "Tablet": 400, "Monitor": 250, "Keyboard": 40}).values
    qty = rng.integers(1, 6, n)
    disc = np.where(rng.random(n) < .3, rng.choice([5, 10, 15], n), 0)
    amount = (price * qty * (1 - disc / 100) * rng.normal(1, .05, n)).round(2)
    return pd.DataFrame({
        "order_id": [f"ORD-{100000 + i}" for i in range(n)], "order_date": dates,
        "ship_date": dates + pd.to_timedelta(rng.integers(1, 9, n), "D"),
        "region": region, "product": product, "channel": rng.choice(["Online", "Store", "Partner"], n),
        "quantity": qty, "unit_price": price, "discount_pct": disc, "amount": amount,
        "customer_email": [f"user{rng.integers(1, 900)}@example.com" for _ in range(n)],
        "returned": rng.choice(["Yes", "No"], n, p=[.06, .94]),
    })


def opportunity_demo(seed=7, n=300, m=30000):
    """Opportunities (33 cols) + applications (aap ke jese columns) demo."""
    rng = np.random.default_rng(seed)
    oc = ("pk opportunity_id Badge CareerAddOn category code Cohort created_at currency_type current_editor "
          "DropoutTransaction duration duration_type Eligibility fee image_link is_archived is_auto_approve "
          "last_date_to_apply location long_description microscholarship modified_at name NotStartedTransaction "
          "Panellist Reward role role_responsibility short_description summary Testimonial tracking_questions").split()
    o = pd.DataFrame({c: [None] * n for c in oc})
    o["pk"] = [f"OPPORTUNITY#{1000 + i}" for i in range(n)]
    o["opportunity_id"] = range(1000, 1000 + n)
    o["category"] = rng.choice(["Internship", "Scholarship", "Job", "Course"], n)
    o["created_at"] = pd.to_datetime(rng.choice(pd.date_range("2025-06-01", "2026-03-31"), n)).astype(str)
    o["modified_at"] = o["created_at"]
    o["is_archived"] = rng.choice([True, False], n, p=[.2, .8])
    o["Reward"] = rng.choice(["Rs. 5,000", "Rs. 10,000", "25000", "Certificate", None], n)
    o["microscholarship"] = rng.choice(["0", "1", "Yes", "No", None, "[]"], n)
    o["name"] = [f"Opportunity {i}" for i in range(n)]
    ids = o.opportunity_id.values
    w = rng.pareto(1.5, n) + 0.1
    w /= w.sum()
    ac = ("pk sk assigned_cohort fee status accept_reject_date apply_date from_where_did_you_hear_about_us "
          "completion_date application_id modified_at created_at work_item_sk "
          "how_did_you_hear_about_this_opportunity dropped_out_date").split()
    a = pd.DataFrame({c: [None] * m for c in ac})
    a["application_id"] = [f"APP{i}" for i in range(m)]
    a["pk"] = [f"USER#{i % 9000}" for i in range(m)]
    a["sk"] = [f"APPLICATION#{i}" for i in range(m)]
    a["work_item_sk"] = "OPPORTUNITY#" + pd.Series(rng.choice(ids, m, p=w)).astype(str)
    a["apply_date"] = pd.to_datetime(rng.choice(pd.date_range("2025-06-01", "2026-03-31"), m)).astype(str)
    a["created_at"] = a["apply_date"]
    a["modified_at"] = a["apply_date"]
    a["status"] = rng.choice(["Applied", "Accepted", "Rejected", "Completed", "Withdrawn"], m, p=[.3, .3, .15, .2, .05])
    a["completion_date"] = np.where(rng.random(m) < .25, "2026-02-01", None)
    a["from_where_did_you_hear_about_us"] = rng.choice(["Instagram", "LinkedIn", "friend", None, None, "WhatsApp group"], m)
    a["how_did_you_hear_about_this_opportunity"] = rng.choice(["linkedin", "University", "Facebook", None, None, None], m)
    return o, a
