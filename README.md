# Data Insight Studio

Upload any Excel/CSV file and get automatic cleaning, column-type detection, KPIs, charts, pivot tables, measures,
pattern insights and an SQL console. Includes the **Opportunity Dashboard** (sign-ups, completion, rewards, scholarships,
lead sources, SQL-validated KPIs) as a ready-made page.

## Folder structure

```
data_insight_studio/
├── app.py                      Home: upload files, cleaning options, sample data
├── pages/
│   ├── 1_Overview.py           KPI cards, auto insights, detected schema, data quality, Excel report
│   ├── 2_Charts.py             Auto charts (with "why") + chart builder
│   ├── 3_Pivot_Tables.py       Excel-style pivots: rows/columns/value/agg/% of total/date grouping/export
│   ├── 4_Measures.py           Auto + custom measures (aggregate, ratio), slice by field or time
│   ├── 5_Patterns.py           Trends, correlations, associations, concentration, funnel, outliers
│   ├── 6_SQL_Console.py        SQL on your uploaded tables (SQLite)
│   └── 7_Opportunity_Dashboard.py   Preset dashboard for opportunities + applications tables
├── core/                       Generic engine (no Streamlit needed except state.py / ui.py)
│   ├── loader.py               Excel/CSV -> tables (all sheets, header-row detection)
│   ├── cleaner.py              Trim, null-like values, HTML, text->numbers/dates, duplicates
│   ├── detector.py             Column roles: id / datetime / measure / category / boolean / text ...
│   ├── analysis.py             KPIs, time series, correlations, Cramer's V, outliers, insights
│   ├── pivot.py  measures.py  charts.py  sample.py  state.py  ui.py
├── presets/opportunity/        Your existing dashboard, packaged
│   ├── config.py               Column mapping (also editable in the page UI)
│   ├── data_prep.py            Cleaning + auto-join of applications to opportunities
│   ├── metrics.py              Every dashboard metric + rule-based insights
│   ├── validate.py             SQL re-check of every KPI (PASS/FAIL report)
│   └── view.py                 The dashboard UI
├── scripts/                    run_opportunity_validation.py, make_sample_excel.py
├── sample_data/                Demo Excel files to try the upload
├── tests/                      pytest: engine + every page headless
├── .streamlit/config.toml      200 MB upload limit, theme
├── requirements.txt  Dockerfile  .gitignore
```

## Run locally

```
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Open the URL shown, upload your Excel file(s) on **Home**, then use the pages in the left sidebar.
For the opportunity dashboard upload both the opportunities and applications workbooks, then open page 7.
The two tables are matched automatically (the join column is detected; check the cleaning log).

## Put the app online (so you can upload from anywhere)

1. Create a GitHub repository and push this folder (`git init`, `git add .`, `git commit`, `git push`).
2. Go to share.streamlit.io, sign in with GitHub, choose the repo, main file `app.py`, and deploy.
3. Or with Docker: `docker build -t insight-studio .` then `docker run -p 8501:8501 insight-studio`.

Uploaded data stays in the user's session memory only; nothing is written to disk. If the data is sensitive, deploy
privately (Streamlit Cloud private app, or inside your own network) rather than on a public URL.

## Tests

```
python -m pytest tests -q
```

## Known limits

- Auto-detection is heuristic. If a column type is wrong, see Overview > Schema and clean the file or tell me.
- Day-first dates (31/12/2025) need the "day-first" checkbox on Home.
- Very large files (hundreds of thousands of rows) work but upload and parsing of .xlsx is slow; CSV is faster.
- Insights are rule-based drafts. Confirm with business context before acting on them.
