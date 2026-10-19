"""Demo Excel files banao (sample_data/ mein):  python scripts/make_sample_excel.py"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core import sample  # noqa: E402

out = ROOT / "sample_data"
out.mkdir(exist_ok=True)
sample.sales_demo().to_excel(out / "sales_demo.xlsx", index=False)
o, a = sample.opportunity_demo()
o.to_excel(out / "opportunities_demo.xlsx", index=False)
a.to_excel(out / "applications_demo.xlsx", index=False)
print("Created:", *sorted(p.name for p in out.glob("*.xlsx")))
