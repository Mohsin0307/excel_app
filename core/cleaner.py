"""Generic data cleaning: spaces, null-jesi strings, HTML, numbers/dates jo text bane hon, duplicates."""
import html
import re
import warnings

import pandas as pd

NULLS = {"", "nan", "none", "null", "n/a", "na", "#n/a", "-", "--", "nil", "<na>", "undefined"}
DATE_NAME = re.compile(r"(date|time|_at$|_on$|timestamp|created|modified|updated|dob|deadline)", re.I)
DATE_VALUE = re.compile(r"^\s*(\d{4}[-/.]\d{1,2}[-/.]\d{1,2}|\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4})([ T]\d{1,2}:\d{2}.*)?\s*$")
CURRENCY = re.compile(r"^(rs\.?|pkr|usd|inr|eur|gbp|aed|[$€£₹])\s*", re.I)


def _is_text(s):
    return str(s.dtype) in ("object", "string", "str")


def _to_number(s):
    t = s.astype("string").str.strip().str.replace(CURRENCY, "", regex=True)
    t = t.str.replace(r"[,\s]", "", regex=True).str.replace(r"%$", "", regex=True)
    return pd.to_numeric(t, errors="coerce")


def _to_datetime(s, dayfirst=False):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        d = pd.to_datetime(s, errors="coerce", utc=True, dayfirst=dayfirst)
    return d.dt.tz_localize(None)


def clean(df, drop_duplicates=True, parse_numbers=True, parse_dates=True, strip_html=True, dayfirst=False):
    """Return (clean_df, log_lines)."""
    df = df.copy()
    log = [f"Start: {len(df):,} rows x {df.shape[1]} columns"]
    converted_num, converted_date, html_cols, blanked = [], [], [], 0

    for c in [c for c in df.columns if _is_text(df[c])]:
        s = df[c].astype("string").str.strip().str.replace(r"\s+", " ", regex=True)
        isnull = s.str.lower().isin(NULLS).fillna(False)
        blanked += int((isnull & s.notna()).sum())
        s = s.mask(isnull)
        nn = s.dropna()
        if nn.empty:
            df[c] = s
            continue
        sample = nn.head(2000)

        if strip_html and sample.str.contains(r"<[a-zA-Z/][^>]*>", regex=True).mean() > 0.1:
            s = s.map(lambda x: x if pd.isna(x) else re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", x))).strip())
            html_cols.append(c)
            sample = s.dropna().head(2000)

        if parse_dates and (DATE_VALUE.match(str(sample.iloc[0])) or DATE_NAME.search(c)) \
                and sample.str.match(DATE_VALUE).mean() >= 0.8:
            d = _to_datetime(s, dayfirst)
            if d.notna().sum() >= 0.9 * s.notna().sum():
                df[c] = d
                converted_date.append(c)
                continue

        if parse_numbers:
            leading_zero = sample.str.match(r"^0\d").mean() > 0.05  # codes/phone numbers
            n = _to_number(s)
            if not leading_zero and n.notna().sum() >= 0.95 * s.notna().sum():
                df[c] = n
                converted_num.append(c)
                continue
        df[c] = s

    if blanked:
        log.append(f"Blank-like values (empty, 'null', 'N/A', '-' ...) set to missing: {blanked:,}")
    if html_cols:
        log.append(f"HTML tags removed: {html_cols}")
    if converted_num:
        log.append(f"Text converted to numbers: {converted_num}")
    if converted_date:
        log.append(f"Text converted to dates: {converted_date}")
    if drop_duplicates:
        n0 = len(df)
        df = df.drop_duplicates().reset_index(drop=True)
        log.append(f"Exact duplicate rows removed: {n0 - len(df):,}")
    log.append(f"Result: {len(df):,} rows x {df.shape[1]} columns")
    return df, log
