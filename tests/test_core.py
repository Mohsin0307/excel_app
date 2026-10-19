import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import analysis as an  # noqa: E402
from core import cleaner, detector as dt, loader, measures as ms, pivot, sample  # noqa: E402


def _sales():
    df = sample.sales_demo(1500)
    clean, _ = cleaner.clean(df)
    return clean, dt.detect_roles(clean)


def test_loader_header_row_and_unnamed(tmp_path):
    raw = pd.DataFrame([["Report title", None, None], [None, None, None], ["a", "b", "c"], [1, 2, 3], [4, 5, 6]])
    p = tmp_path / "x.xlsx"
    raw.to_excel(p, header=False, index=False)
    t = loader.read_file("x.xlsx", p.read_bytes())
    df = next(iter(t.values()))
    assert list(df.columns) == ["a", "b", "c"] and len(df) == 2


def test_cleaner_converts_text_numbers_and_dates():
    df = pd.DataFrame({"fee": ["Rs. 1,000", "2,500", "n/a", "3,000"] * 10,
                       "when": ["2025-01-05", "2025-02-10", "2025-03-01", "2025-03-09"] * 10,
                       "code": ["007", "012", "034", "099"] * 10})
    c, _ = cleaner.clean(df, drop_duplicates=False)
    assert pd.api.types.is_numeric_dtype(c.fee) and c.fee.notna().sum() == 30 and c.fee.sum() == 10 * 6500
    assert pd.api.types.is_datetime64_any_dtype(c.when)
    assert c.code.iloc[0] == "007"  # leading zeros preserved


def test_detector_roles():
    df, prof = _sales()
    r = prof.set_index("column").role
    assert r["order_id"] == "id" and r["order_date"] == "datetime" and r["amount"] == "measure"
    assert r["region"] == "category" and r["returned"] == "boolean"
    assert dt.primary_date(df, prof) == "order_date"


def test_pivot_totals_match_data():
    df, _ = _sales()
    pv = pivot.build_pivot(df, ["region"], ["channel"], "amount", "sum")
    assert abs(pv.loc["Total", "Total"] - df.amount.sum()) < 1e-6
    cnt = pivot.build_pivot(df, ["region"], None, None, "count")
    assert cnt.loc["Total"].iloc[0] == len(df)


def test_pivot_percent_sums_to_100():
    df, _ = _sales()
    pv = pivot.build_pivot(df, ["region"], None, None, "count", show="% of grand total", margins=False)
    assert abs(pv.values.sum() - 100) < 0.1


def test_measures_ratio_and_by_group():
    df, prof = _sales()
    m = {"name": "return rate", "type": "ratio", "percent": True,
         "numerator": {"agg": "count rows", "column": None, "filters": [{"column": "returned", "op": "=", "value": "Yes"}]},
         "denominator": {"agg": "count rows", "column": None, "filters": []}}
    assert abs(ms.evaluate(df, m) - (df.returned == "Yes").mean() * 100) < 1e-9
    by = ms.evaluate_by(df, m, "region")
    assert set(by.group) == set(df.region.unique())
    assert len(ms.suggest_measures(df, prof)) >= 5


def test_analysis_outputs():
    df, prof = _sales()
    assert len(an.kpi_cards(df, prof)) >= 5
    ts = an.time_series(df, "order_date", "M")
    assert ts.value.sum() == len(df)
    assert any(i["type"] == "trend" for i in an.generate_insights(df, prof))
    assert len(an.correlation_pairs(df, dt.measures(prof), 0.3)) >= 1
