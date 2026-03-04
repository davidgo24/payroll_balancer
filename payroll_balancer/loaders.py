"""
Input loaders — TCP CSV and Accrual Excel.
"""
import hashlib
import re
from io import BytesIO
from typing import Any

import pandas as pd


def parse_date_flexible(s: str) -> str:
    """
    Parse date flexibly: YYYY-MM-DD or M/D/YYYY.
    Returns YYYY-MM-DD string.
    """
    s = str(s).strip()
    # YYYY-MM-DD
    if re.match(r"^\d{4}-\d{1,2}-\d{1,2}$", s):
        try:
            dt = pd.to_datetime(s)
            return dt.strftime("%Y-%m-%d")
        except Exception:
            pass
    # M/D/YYYY
    if re.match(r"^\d{1,2}/\d{1,2}/\d{4}$", s):
        try:
            dt = pd.to_datetime(s, format="mixed")
            return dt.strftime("%Y-%m-%d")
        except Exception:
            pass
    try:
        dt = pd.to_datetime(s)
        return dt.strftime("%Y-%m-%d")
    except Exception:
        raise ValueError(f"Cannot parse date: {s!r}")


def load_tcp_csv(content: bytes | str) -> tuple[pd.DataFrame, str]:
    """
    Load TCP export CSV. No header row.
    Columns (positional): emp_id, hrs, code, date
    Returns (DataFrame with emp_id, hrs, code, date), file_hash.
    """
    if isinstance(content, str):
        content = content.encode("utf-8")
    file_hash = hashlib.sha256(content).hexdigest()

    df = pd.read_csv(
        BytesIO(content),
        header=None,
        names=["emp_id", "hrs", "code", "date"],
        dtype={"emp_id": str, "hrs": float, "code": str},
    )

    # Parse dates
    df["date"] = df["date"].astype(str).apply(parse_date_flexible)

    return df, file_hash


def load_accrual_excel(content: bytes) -> dict[str, dict[str, float]]:
    """
    Load AccrualBalanceReport.xlsx.
    Header row 1: Employee (emp_id), name, ADMIN LV, AL, ..., COMP, HOLIDAY, SICK, VAC
    Skip non-data rows (e.g. "Primary Department").
    Negative balances = exhausted (treated as 0 for availability).
    Returns: {emp_id: {"name": str, "AL": float, "COMP": float, "HOLIDAY": float, "SICK": float, "VAC": float}}
    """
    df = pd.read_excel(BytesIO(content), header=1)
    # AccrualBalanceReport: row 1 = header (Employee, AL, COMP, HOLIDAY, SICK, VAC)
    result: dict[str, dict[str, Any]] = {}
    for _, row in df.iterrows():
        val = row.iloc[0]
        if pd.isna(val):
            continue
        try:
            emp_id = str(int(float(val))).strip()
        except (ValueError, TypeError):
            s = str(val).strip()
            if s.startswith("Primary Department") or not s:
                continue
            emp_id = s
        if not emp_id or emp_id == "nan":
            continue
        name = str(row.iloc[1]) if pd.notna(row.iloc[1]) else ""
        if name == "nan":
            name = ""
        # Column indices: 3=AL, 6=COMP, 7=HOLIDAY, 8=SICK, 9=VAC
        def _val(i: int) -> float:
            v = row.iloc[i]
            if pd.isna(v):
                return 0.0
            try:
                f = float(v)
                return max(0.0, f)
            except (ValueError, TypeError):
                return 0.0

        result[emp_id] = {
            "name": name,
            "AL": _val(3),
            "COMP": _val(6),
            "HOLIDAY": _val(7),
            "SICK": _val(8),
            "VAC": _val(9),
        }
    return result
