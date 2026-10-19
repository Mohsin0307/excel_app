"""
CLI: data/ folder ki Excel files par SQL validation chalao.
    python scripts/run_opportunity_validation.py
Output: output/validation_report.csv, output/validation_queries.sql
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from presets.opportunity import config as cfg  # noqa: E402
from presets.opportunity import data_prep as dp  # noqa: E402
from presets.opportunity import validate  # noqa: E402

cfg.DATA_DIR = ROOT / "data"
out = ROOT / "output"
out.mkdir(exist_ok=True)
d = dp.load_all()
print("\n".join(d["log"]))
rep, sql = validate.run(d["opps"], d["apps"])
rep.to_csv(out / "validation_report.csv", index=False)
(out / "validation_queries.sql").write_text(sql, encoding="utf-8")
print(rep.to_string(index=False))
fails = int((rep.status == "FAIL").sum())
print(f"\n{len(rep) - fails}/{len(rep)} checks passed.")
sys.exit(1 if fails else 0)
