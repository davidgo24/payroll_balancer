"""
Week split — Sun–Sat week bucketing, period start derivation.
Biweekly = 14 days = two Sun–Sat weeks.
"""
from datetime import datetime, timedelta


def period_end_to_start(period_end_date: str) -> str:
    """Derive period_start_date = period_end_date - 13 days."""
    dt = datetime.strptime(period_end_date, "%Y-%m-%d")
    start = dt - timedelta(days=13)
    return start.strftime("%Y-%m-%d")


def is_saturday(date_str: str) -> bool:
    """Check if date is a Saturday (period end validation)."""
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    return dt.weekday() == 5


def get_week_number(date_str: str, period_start: str) -> int:
    """
    Return 1 or 2: week 1 = first Sun–Sat, week 2 = second Sun–Sat.
    Period start is day 1 of week 1 (Sunday).
    """
    d = datetime.strptime(date_str, "%Y-%m-%d")
    p_start = datetime.strptime(period_start, "%Y-%m-%d")
    delta = (d - p_start).days
    if delta < 0:
        return 0
    if delta < 7:
        return 1
    if delta < 14:
        return 2
    return 0


def get_week_start_end(period_start: str, week: int) -> tuple[str, str]:
    """Return (week_start_date, week_end_date) for week 1 or 2."""
    p = datetime.strptime(period_start, "%Y-%m-%d")
    if week == 1:
        start = p
        end = p + timedelta(days=6)
    else:
        start = p + timedelta(days=7)
        end = p + timedelta(days=13)
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")
