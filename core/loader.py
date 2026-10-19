"""Uploaded Excel/CSV files ko DataFrames mein badalta hai (har sheet alag table)."""
import io
import re

import pandas as pd

MAX_ROWS_WARN = 500_000


def _unique_names(cols):
    seen, out = {}, []
    for i, c in enumerate(cols):
        c = re.sub(r"\s+", " ", str(c)).strip()
        if not c or c.lower() == "nan" or re.fullmatch(r"unnamed: \d+", c.lower()):
            c = f"column_{i + 1}"
        n = seen.get(c, 0)
        seen[c] = n + 1
        out.append(c if n == 0 else f"{c}_{n + 1}")
    return out


def _promote_header(raw):
    """Header=None wali sheet mein asli header row dhoondo (upar title/khali rows ho sakti hain)."""
    scan = raw.head(15)
    fill = scan.notna().mean(axis=1)
    strs = scan.apply(lambda r: r.dropna().map(lambda x: isinstance(x, str)).mean() if r.notna().any() else 0, axis=1)
    ok = [i for i in range(len(scan)) if fill.iloc[i] >= 0.6 * fill.max() and strs.iloc[i] >= 0.8]
    h = ok[0] if ok else 0
    df = raw.iloc[h + 1:].copy()
    df.columns = raw.iloc[h].tolist()
    return df.infer_objects()


def tidy(df):
    df = df.copy()
    df.columns = _unique_names(df.columns)
    df = df.dropna(how="all").dropna(axis=1, how="all")
    return df.reset_index(drop=True)


def read_file(name, data):
    """name = file name, data = bytes. Return {table_name: DataFrame}."""
    base = name.rsplit(".", 1)[0]
    ext = name.lower().rsplit(".", 1)[-1]
    if ext in ("csv", "txt"):
        df = pd.read_csv(io.BytesIO(data), sep=None, engine="python", encoding_errors="replace")
        return {base: tidy(df)}
    if ext not in ("xlsx", "xlsm", "xls"):
        raise ValueError(f"Unsupported file type: .{ext}")
    sheets = pd.read_excel(io.BytesIO(data), sheet_name=None)
    out = {}
    multi = len(sheets) > 1
    for sh, df in sheets.items():
        unnamed = sum(str(c).lower().startswith("unnamed") for c in df.columns) / max(len(df.columns), 1)
        if unnamed >= 0.5:  # header pehli row mein nahi hai
            df = _promote_header(pd.read_excel(io.BytesIO(data), sheet_name=sh, header=None))
        df = tidy(df)
        if df.empty:
            continue
        out[f"{base} | {sh}" if multi else base] = df
    if not out:
        raise ValueError("File mein koi data nahi mila.")
    return out
