"""Har page ko headless chalao (Streamlit AppTest) aur dekho koi exception na aaye."""
import sys
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core import cleaner, sample  # noqa: E402

OPTS = dict(drop_duplicates=True, parse_numbers=True, parse_dates=True, strip_html=True, dayfirst=False)


def _entry(raw):
    clean, log = cleaner.clean(raw, **OPTS)
    return {"raw": raw, "clean": clean, "log": log}


def _run(page, datasets, active, timeout=180):
    at = AppTest.from_file(str(ROOT / page), default_timeout=timeout)
    at.session_state["datasets"] = datasets
    at.session_state["active"] = active
    return at.run()


@pytest.fixture(scope="module")
def sales():
    return {"sales": _entry(sample.sales_demo(2000))}


@pytest.mark.parametrize("page", ["pages/1_Overview.py", "pages/2_Charts.py", "pages/3_Pivot_Tables.py",
                                  "pages/4_Measures.py", "pages/5_Patterns.py", "pages/6_SQL_Console.py"])
def test_generic_pages(page, sales):
    at = _run(page, sales, "sales")
    assert not at.exception, [e.value for e in at.exception]


def test_pages_without_data_show_hint():
    at = AppTest.from_file(str(ROOT / "pages/1_Overview.py"), default_timeout=60).run()
    assert not at.exception and any("No data yet" in i.value for i in at.info)


def test_home_sample_button():
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=120).run()
    next(b for b in at.button if "sales sample" in b.label).click().run()
    assert not at.exception and "sales_demo" in at.session_state["datasets"]


def test_opportunity_page():
    o, a = sample.opportunity_demo(n=150, m=8000)
    ds = {"opportunities_demo": _entry(o), "applications_demo": _entry(a)}
    at = _run("pages/7_Opportunity_Dashboard.py", ds, "opportunities_demo")
    assert not at.exception, [e.value for e in at.exception]
    labels = [m.label for m in at.metric]
    assert "Sign-ups" in labels and "Completion rate" in labels
    next(b for b in at.button if b.label == "Run SQL validation").click().run()
    assert not at.exception
    v, _ = at.session_state["opp_validation"]
    assert (v.status == "PASS").all(), v[v.status != "PASS"]


def test_opportunity_page_without_applications():
    o, _ = sample.opportunity_demo(n=150, m=100)
    at = _run("pages/7_Opportunity_Dashboard.py", {"opps": _entry(o)}, "opps")
    assert not at.exception, [e.value for e in at.exception]
