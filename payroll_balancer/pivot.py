"""
Pivot builder — internal long format to grid for display.
Rows = date (+ day-of-week), columns = pay codes.
"""
import pandas as pd
from datetime import datetime


def pivot_to_grid(df: pd.DataFrame) -> dict:
    """
    Pivot long format (emp_id, date, code, hrs) to grid structure.
    Sum hours when multiple rows share same emp+date+code.
    Returns structure suitable for UI: {emp_id: {dates: [...], codes: [...], cells: {date: {code: hrs}}}}
    Per spec: we pivot by date rows and code columns. For display we need dates + codes + values.
    """
    if df.empty:
        return {"dates": [], "codes": [], "cells": {}}

    # Aggregate same emp+date+code
    agg = df.groupby(["emp_id", "date", "code"], as_index=False)["hrs"].sum()

    dates = sorted(agg["date"].unique())
    codes = sorted(agg["code"].unique())

    cells: dict[str, dict[str, dict[str, float]]] = {}
    for (emp_id, date, code), group in agg.groupby(["emp_id", "date", "code"]):
        hrs = group["hrs"].sum()
        if emp_id not in cells:
            cells[emp_id] = {}
        if date not in cells[emp_id]:
            cells[emp_id][date] = {}
        cells[emp_id][date][code] = round(hrs, 2)

    return {"dates": dates, "codes": codes, "cells": cells}


def format_date_ui(date_str: str) -> str:
    """UI date format M/D/YYYY."""
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    return f"{dt.month}/{dt.day}/{dt.year}"


def add_day_of_week(dates: list[str]) -> list[dict]:
    """Add day-of-week for display. Returns [{date, display, dow}, ...]"""
    result = []
    for d in dates:
        dt = datetime.strptime(d, "%Y-%m-%d")
        dow = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][dt.weekday()]
        result.append({"date": d, "display": format_date_ui(d), "dow": dow})
    return result
