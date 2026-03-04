"""Test leave fallback order."""
import pandas as pd

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from payroll_balancer.rules.leave_check import leave_check


def get_week(date_str: str, period_start: str) -> int:
    from payroll_balancer.week_split import get_week_number
    return get_week_number(date_str, period_start)


def test_sick_to_vac_fallback():
    df = pd.DataFrame([
        {"emp_id": "1020", "date": "2026-02-22", "hrs": 8, "code": "SICK PAY"},
    ])
    accrual = {"1020": {"SICK": 4, "VAC": 10, "AL": 5, "COMP": 2}}
    period_start = "2026-02-16"
    suggestions = leave_check(df, accrual, period_start, get_week)
    assert len(suggestions) == 1
    s = suggestions[0]
    assert s["original_code"] == "SICK PAY"
    assert s["proposed_code"] == "VAC PAY"
    assert s["proposed_hrs"] == 4.0
    assert "fallback" in s["reason"].lower() or "VAC" in s["reason"]


def test_sick_to_lwop_when_no_fallback():
    df = pd.DataFrame([
        {"emp_id": "1020", "date": "2026-02-22", "hrs": 8, "code": "SICK PAY"},
    ])
    accrual = {"1020": {"SICK": 0, "VAC": 0, "AL": 0, "COMP": 0}}
    period_start = "2026-02-16"
    suggestions = leave_check(df, accrual, period_start, get_week)
    assert len(suggestions) == 1
    s = suggestions[0]
    assert s["proposed_code"] == "LWOP"
    assert s["proposed_hrs"] == 8.0
