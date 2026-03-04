"""
Rule 1 — Leave check (period-scope exhaustion).
Compute leave used per bank over entire period vs accrual balances.
Suggest reallocation to fallback bank or LWOP when insufficient.
Process rows in date order; track running balances for fallbacks.
"""
import pandas as pd

from payroll_balancer.config.codes import (
    BANK_DRAWS,
    BANK_FALLBACK_ORDER,
    BANK_TO_DEFAULT_CODE,
    code_draws_from_bank,
)


def get_bank_balances(accrual: dict[str, dict], emp_id: str) -> dict[str, float]:
    """Get leave bank balances for employee. Missing = all 0."""
    if emp_id not in accrual:
        return {"SICK": 0.0, "VAC": 0.0, "AL": 0.0, "COMP": 0.0}
    r = accrual[emp_id]
    return {
        "SICK": float(r.get("SICK", 0)),
        "VAC": float(r.get("VAC", 0)),
        "AL": float(r.get("AL", 0)),
        "COMP": float(r.get("COMP", 0)),
    }


def leave_check(
    df: pd.DataFrame,
    accrual: dict[str, dict],
    period_start: str,
    get_week_fn,
) -> list[dict]:
    """
    Rule 1: Period-scope leave exhaustion.
    Process rows in date order; when bank exhausted, try fallbacks (consuming their balance).
    Returns suggestions.
    """
    suggestions = []

    for emp_id, emp_df in df.groupby("emp_id"):
        balances = {k: v for k, v in get_bank_balances(accrual, emp_id).items()}

        # Only leave rows, sorted by date
        leave_rows = []
        for _, row in emp_df.iterrows():
            code = str(row["code"]).strip()
            bank = code_draws_from_bank(code)
            if bank:
                leave_rows.append((row, bank))

        leave_rows.sort(key=lambda x: (str(x[0]["date"]), x[0]["code"]))

        for row, bank in leave_rows:
            hrs = float(row["hrs"])
            date = str(row["date"])
            code = str(row["code"])
            week = get_week_fn(date, period_start)

            if balances.get(bank, 0) >= hrs:
                balances[bank] -= hrs
                continue

            excess = round(hrs - balances.get(bank, 0), 2)
            balances[bank] = 0

            # Week-level: use full fallback banks before LWOP (partial allocation per fallback)
            fallbacks = BANK_FALLBACK_ORDER.get(bank, ["LWOP"])
            for fb in fallbacks:
                if excess <= 0:
                    break
                if fb == "LWOP":
                    suggestions.append({
                        "emp_id": emp_id,
                        "date": date,
                        "week": week,
                        "original_code": code,
                        "original_hrs": round(hrs, 2),
                        "proposed_code": "LWOP",
                        "proposed_hrs": round(excess, 2),
                        "reason": f"Insufficient {bank}/VAC/COMP/AL → unpaid (document to 40)",
                        "severity": "HIGH",
                    })
                    excess = 0
                    break
                fb_bal = balances.get(fb, 0)
                if fb_bal > 0:
                    use_amt = round(min(excess, fb_bal), 2)
                    balances[fb] -= use_amt
                    excess -= use_amt
                    suggestions.append({
                        "emp_id": emp_id,
                        "date": date,
                        "week": week,
                        "original_code": code,
                        "original_hrs": round(hrs, 2),
                        "proposed_code": BANK_TO_DEFAULT_CODE.get(fb, fb),
                        "proposed_hrs": use_amt,
                        "reason": f"Insufficient {bank} → fallback to {BANK_TO_DEFAULT_CODE.get(fb, fb)}",
                        "severity": "HIGH",
                    })

    return suggestions
