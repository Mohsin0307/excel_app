"""
Opportunity + learner data: read -> clean -> tables -> pie charts

Folder structure:
    excel/
        clean_and_analyze.py
        data/                     <- .xlsx aur .csv files yahan rakho
        output/                   <- har input file ka apna folder

Run:  python clean_and_analyze.py
      python clean_and_analyze.py path/to/one_file.xlsx
"""
import html
import re
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

# ----------------------------------------------------------------------
# 0. Paths
# ----------------------------------------------------------------------
BASE = Path(__file__).resolve().parent
DATA_DIR = BASE / "data"
OUT_DIR = BASE / "output"
OUT_DIR.mkdir(parents=True, exist_ok=True)

DATE_CANDIDATES = [
    "created_at",
    "modified_at",
    "last_date_to_apply",
    "apply_date",
    "accept_reject_date",
    "not_started_date",
    "reward_awarded_date",
    "completion_date",
    "withdraw_date",
    "dropped_out_date",
]
NUM_CANDIDATES = ["fee", "duration", "amount_to_be_paid"]
HTML_CANDIDATES = [
    "long_description",
    "short_description",
    "summary",
    "role_responsibility",
    "Eligibility",
    "Reward",
    "Testimonial",
    "why_do_you_want_to_apply_for_this_internship",
    "why_do_you_want_to_apply_for_this_internship1",
    "can_you_share_an_experience_where_you_proactively_pursued_learn",
]
COUNT_TABLE_COLS = [
    "category",
    "currency_type",
    "duration_type",
    "is_archived",
    "is_auto_approve",
    "Cohort",
    "role",
    "microscholarship",
    "CareerAddOn",
    "status",
    "payment_status",
    "assigned_cohort",
    "from_where_did_you_hear_about_us",
    "cohort_p1",
    "cohort_p2",
    "appear_in_wishlist",
    "please_identify_your_student_status",
]
CHART_COLS = {
    "category": "By Category",
    "currency_type": "By Currency",
    "duration_type": "By Duration Type",
    "is_archived": "Archived vs Active",
    "is_auto_approve": "Auto-Approve vs Manual",
    "Cohort": "By Cohort",
    "location": "By Location (Top 8)",
    "role": "By Role (Top 8)",
    "status": "By Status",
    "payment_status": "By Payment Status",
    "assigned_cohort": "By Assigned Cohort",
    "from_where_did_you_hear_about_us": "How Applicants Heard (Top 8)",
    "appear_in_wishlist": "Wishlist Flag",
}
# pehle match hone wala rule use hota hai
ID_RULES = [
    ["opportunity_id"],
    ["pk", "sk"],
    ["application_id"],
    ["sk"],
]


def find_input_files():
    if len(sys.argv) > 1:
        return [Path(p) for p in sys.argv[1:]]

    files = []
    for pattern in ("*.xlsx", "*.xlsm", "*.xls", "*.csv"):
        files.extend(DATA_DIR.glob(pattern))
    files = [
        f
        for f in files
        if not f.name.startswith("~$") and f.suffix.lower() != ".xlsb"
    ]
    files = sorted(set(files), key=lambda p: p.name.lower())
    if not files:
        sys.exit(f"Koi Excel/CSV file nahi mili: {DATA_DIR}")
    return files


def output_slug(path: Path) -> str:
    name = path.name
    for suffix in (".xlsx", ".xlsm", ".xls", ".csv"):
        if name.lower().endswith(suffix):
            name = name[: -len(suffix)]
            break
    name = name.replace("#Learner Data.xlsx - #", "")
    name = re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_").lower()
    return name or "dataset"


def read_table(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path, low_memory=False)
    return pd.read_excel(path)


def strip_html(x):
    if pd.isna(x):
        return x
    x = re.sub(r"<[^>]+>", " ", str(x))
    x = html.unescape(x)
    return re.sub(r"\s+", " ", x).strip()


def to_datetime_smart(series: pd.Series) -> pd.Series:
    """ISO strings aur epoch (seconds / milliseconds) dono handle karo."""
    raw = series.copy()
    numeric = pd.to_numeric(raw, errors="coerce")
    n_num = numeric.notna().sum()
    n_non_null = raw.notna().sum()

    if n_non_null and n_num / n_non_null >= 0.5:
        sample = numeric.dropna()
        if sample.empty:
            parsed = pd.to_datetime(raw, errors="coerce", utc=True)
        else:
            med = sample.abs().median()
            unit = "ms" if med >= 1e11 else "s"
            parsed = pd.to_datetime(numeric, unit=unit, errors="coerce", utc=True)
        return parsed.dt.tz_localize(None)

    parsed = pd.to_datetime(raw, errors="coerce", utc=True)
    return parsed.dt.tz_localize(None)


def pie_chart(series, title, filename, out_charts: Path, top_n=8):
    s = series.fillna("Missing").astype(str).value_counts()
    if len(s) > top_n:
        s = pd.concat([s.head(top_n), pd.Series({"Other": s.iloc[top_n:].sum()})])
    fig, ax = plt.subplots(figsize=(8, 6))
    wedges, _, _ = ax.pie(
        s.values,
        autopct=lambda p: f"{p:.1f}%" if p >= 3 else "",
        startangle=90,
        counterclock=False,
        pctdistance=0.8,
    )
    ax.legend(
        wedges,
        [f"{k} ({v})" for k, v in s.items()],
        title=series.name,
        loc="center left",
        bbox_to_anchor=(1, 0.5),
    )
    ax.set_title(title, fontsize=14, fontweight="bold")
    ax.axis("equal")
    fig.tight_layout()
    fig.savefig(out_charts / filename, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Chart saved: {filename}")


def count_table(df, col, top=None):
    t = df[col].fillna("Missing").astype(str).value_counts().reset_index()
    t.columns = [col, "count"]
    t["percent"] = (t["count"] / t["count"].sum() * 100).round(2)
    return t.head(top) if top else t


def clean_and_analyze(path: Path):
    slug = output_slug(path)
    file_out = OUT_DIR / slug
    chart_dir = file_out / "charts"
    chart_dir.mkdir(parents=True, exist_ok=True)

    print("\n" + "=" * 70)
    print(f"Reading: {path}")
    df = read_table(path)
    print(f"Original shape: {df.shape[0]} rows x {df.shape[1]} columns")

    print("\n--- Columns & dtypes ---")
    print(df.dtypes)
    print("\n--- Missing values (top 10) ---")
    print(df.isna().sum().sort_values(ascending=False).head(10))

    log = []

    def note(msg):
        log.append(msg)
        print(msg)

    df.columns = [str(c).strip() for c in df.columns]

    unnamed = [c for c in df.columns if c.startswith("Unnamed")]
    if unnamed:
        df = df.drop(columns=unnamed)
        note(f"Dropped unnamed/extra columns: {len(unnamed)}")

    text_cols = df.select_dtypes(include=["object", "string"]).columns
    for c in text_cols:
        df[c] = (
            df[c]
            .astype("string")
            .str.strip()
            .str.replace(r"\s+", " ", regex=True)
            .replace({"": pd.NA, "nan": pd.NA, "None": pd.NA, "NULL": pd.NA, "null": pd.NA})
        )

    html_cols = [c for c in HTML_CANDIDATES if c in df.columns]
    for c in html_cols:
        df[c] = df[c].map(strip_html)
    note(f"HTML tags cleaned in: {html_cols}")

    date_cols = [c for c in DATE_CANDIDATES if c in df.columns]
    for c in date_cols:
        df[c] = to_datetime_smart(df[c])
    note(f"Converted to datetime: {date_cols}")

    num_cols = [c for c in NUM_CANDIDATES if c in df.columns]
    for c in num_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    note(f"Converted to numeric: {num_cols}")

    before = len(df)
    df = df.drop_duplicates()
    note(f"Exact duplicate rows removed: {before - len(df)}")

    id_cols = next((cols for cols in ID_RULES if all(c in df.columns for c in cols)), None)
    if id_cols:
        before = len(df)
        sort_col = "modified_at" if "modified_at" in df.columns else None
        if sort_col:
            df = df.sort_values(sort_col)
        df = df.drop_duplicates(subset=id_cols, keep="last")
        df = df.sort_index()
        note(f"Duplicate {', '.join(id_cols)} removed: {before - len(df)}")

    empty_cols = [c for c in df.columns if df[c].isna().all()]
    if empty_cols:
        df = df.drop(columns=empty_cols)
    note(f"Fully empty columns dropped: {empty_cols}")

    before = len(df)
    df = df.dropna(how="all")
    note(f"Fully empty rows dropped: {before - len(df)}")

    df = df.reset_index(drop=True)
    note(f"Cleaned shape: {df.shape[0]} rows x {df.shape[1]} columns")

    missing = pd.DataFrame(
        {
            "column": df.columns,
            "dtype": df.dtypes.astype(str).values,
            "missing_count": df.isna().sum().values,
            "missing_percent": (df.isna().mean() * 100).round(2).values,
            "unique_values": df.nunique().values,
        }
    ).sort_values("missing_percent", ascending=False)

    tables = {}
    for col in COUNT_TABLE_COLS:
        if col in df.columns:
            tables[f"by_{col}"] = count_table(df, col)

    if "location" in df.columns:
        tables["by_location_top20"] = count_table(df, "location", top=20)

    if "fee" in df.columns:
        group = "category" if "category" in df.columns else None
        if group:
            tables["fee_by_category"] = (
                df.groupby(group)["fee"]
                .agg(["count", "mean", "median", "min", "max"])
                .round(2)
                .sort_values("count", ascending=False)
                .reset_index()
            )
        tables["fee_summary"] = (
            df["fee"].describe().round(2).reset_index().rename(columns={"index": "stat", "fee": "value"})
        )

    if "created_at" in df.columns:
        m = df.dropna(subset=["created_at"]).copy()
        if not m.empty:
            m["month"] = m["created_at"].dt.to_period("M").astype(str)
            tables["created_per_month"] = m.groupby("month").size().reset_index(name="count")

    if "apply_date" in df.columns:
        m = df.dropna(subset=["apply_date"]).copy()
        if not m.empty:
            m["month"] = m["apply_date"].dt.to_period("M").astype(str)
            tables["applied_per_month"] = m.groupby("month").size().reset_index(name="count")

    if "last_date_to_apply" in df.columns:
        today = pd.Timestamp.today().normalize()
        status = pd.Series("No deadline", index=df.index)
        status[df["last_date_to_apply"] >= today] = "Open (deadline aage hai)"
        status[df["last_date_to_apply"] < today] = "Expired (deadline guzar gayi)"
        t = status.value_counts().reset_index()
        t.columns = ["deadline_status", "count"]
        tables["deadline_status"] = t

    for col, title in CHART_COLS.items():
        if col in df.columns and df[col].notna().any():
            pie_chart(df[col], title, f"pie_{col}.png", chart_dir)

    if "deadline_status" in tables:
        s = tables["deadline_status"].set_index("deadline_status")["count"]
        fig, ax = plt.subplots(figsize=(7, 5))
        ax.pie(s.values, labels=s.index, autopct="%1.1f%%", startangle=90)
        ax.set_title("Deadline Status", fontsize=14, fontweight="bold")
        fig.savefig(chart_dir / "pie_deadline_status.png", dpi=150, bbox_inches="tight")
        plt.close(fig)

    export_df = df.copy()
    illegal_re = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
    binary_markers = ("Exif", "JFIF", "ICC_PROFILE")

    def sanitize_cell(val):
        if pd.isna(val):
            return val
        text = str(val)
        if any(m in text[:80] for m in binary_markers) or "\x00" in text:
            return pd.NA
        text = illegal_re.sub("", text)
        return text[:32000]

    for c in export_df.select_dtypes(include=["object", "string"]).columns:
        export_df[c] = export_df[c].map(sanitize_cell)

    cleaned_xlsx = file_out / f"cleaned_{slug}.xlsx"
    tables_xlsx = file_out / "summary_tables.xlsx"
    cleaned_csv = file_out / f"cleaned_{slug}.csv"

    with pd.ExcelWriter(cleaned_xlsx, engine="openpyxl") as w:
        export_df.to_excel(w, sheet_name="cleaned_data", index=False)
        missing.to_excel(w, sheet_name="missing_report", index=False)
        pd.DataFrame({"cleaning_log": log}).to_excel(w, sheet_name="cleaning_log", index=False)

    with pd.ExcelWriter(tables_xlsx, engine="openpyxl") as w:
        for name, t in tables.items():
            t.to_excel(w, sheet_name=name[:31], index=False)

    export_df.to_csv(cleaned_csv, index=False, encoding="utf-8-sig")

    print(f"\nDone for {path.name}. Output folder: {file_out}")
    print("Tables created:", ", ".join(tables) if tables else "(none)")
    return slug


def main():
    files = find_input_files()
    print(f"Files to clean: {len(files)}")
    for f in files:
        print(f"  - {f.name}")
    slugs = [clean_and_analyze(f) for f in files]
    print("\n" + "=" * 70)
    print("All files cleaned. Output folders:")
    for s in slugs:
        print(f"  {OUT_DIR / s}")


if __name__ == "__main__":
    main()
