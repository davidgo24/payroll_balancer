"""Test LWOP documents to 40 scenario."""
import pandas as pd

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from payroll_balancer.totals import compute_weekly_totals


def get_week(date_str: str, period_start: str) -> int:
    from payroll_balancer.week_split import get_week_number
    return get_week_number(date_str, period_start)


def test_documented_to_40():
    # Paid 34 + LWOP 6 = 40 documented
    df = pd.DataFrame([
        {"emp_id": "1020", "date": "2026-02-22", "hrs": 34, "code": "REG FT"},
        {"emp_id": "1020", "date": "2026-02-22", "hrs": 6, "code": "LWOP"},
    ])
    period_start = "2026-02-16"
    totals = compute_weekly_totals(df, period_start, get_week)
    w1 = totals["1020"]["week1"]
    assert w1["paid"] == 34.0
    assert w1["lwop"] == 6.0
    assert w1["documented"] == 40.0
