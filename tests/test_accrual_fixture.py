"""Test accrual loader with fixture (minimal AccrualBalanceReport structure)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from payroll_balancer.loaders import load_accrual_excel


def test_load_accrual_fixture():
    path = Path(__file__).parent / "fixtures" / "accrual_sample.xlsx"
    content = path.read_bytes()
    acc = load_accrual_excel(content)
    assert "1020" in acc or "1025" in acc
    # At least one employee should have banks
    for eid, row in acc.items():
        assert "name" in row
        assert "SICK" in row
        assert "VAC" in row
        break
