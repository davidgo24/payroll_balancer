"""Test Sun-Sat week bucketing."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from payroll_balancer.week_split import (
    period_end_to_start,
    is_saturday,
    get_week_number,
)


def test_period_end_to_start():
    assert period_end_to_start("2026-03-14") == "2026-03-01"
    assert period_end_to_start("2026-02-28") == "2026-02-15"


def test_is_saturday():
    assert is_saturday("2026-03-14") is True   # Sat
    assert is_saturday("2026-03-15") is False  # Sun


def test_get_week_number():
    # Period start 2026-03-01 (Sun), end 2026-03-14 (Sat)
    period_start = "2026-03-01"
    assert get_week_number("2026-03-01", period_start) == 1
    assert get_week_number("2026-03-07", period_start) == 1
    assert get_week_number("2026-03-08", period_start) == 2
    assert get_week_number("2026-03-14", period_start) == 2
