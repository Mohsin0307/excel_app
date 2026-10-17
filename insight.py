"""Insights ko file mein likho:  python insights_report.py  -> output/insights.md"""
import config as cfg
import data_prep as dp
import metrics as m

cfg.OUT_DIR.mkdir(parents=True, exist_ok=True)
d = dp.load_all()
md = m.insights_markdown(d["opps"], d["apps"])
(cfg.OUT_DIR / "insights.md").write_text(md, encoding="utf-8")
print(md)