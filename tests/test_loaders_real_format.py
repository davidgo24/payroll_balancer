"""Test loaders with real data format (fixtures)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from payroll_balancer.loaders import load_tcp_csv, load_accrual_excel, parse_date_flexible


def test_parse_date_mdyyyy():
    assert parse_date_flexible("2/23/2026") == "2026-02-23"
    assert parse_date_flexible("2/28/2026") == "2026-02-28"


def test_load_tcp_fixture():
    path = Path(__file__).parent / "fixtures" / "tcp_week1_sample.csv"
    content = path.read_bytes()
    df, h = load_tcp_csv(content)
    assert len(df) == 9
    assert "emp_id" in df.columns
    assert df["date"].iloc[0] == "2026-02-23"
    assert "REG FT" in df["code"].values
    assert "GUARANTEE" in df["code"].values
    assert "SICK PAY" in df["code"].values
