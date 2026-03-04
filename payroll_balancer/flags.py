"""
Flags engine — per employee, per week.
Severity: HIGH / MEDIUM / LOW.
"""
import pandas as pd

from payroll_balancer.config.codes import (
    BANK_DRAWS,
    code_draws_from_bank,
    PREMIUM_CODES,
    LWOP_CODE,
)


def compute_flags(
    df: pd.DataFrame,
    accrual: dict,
    leave_suggestions: list[dict],
    lwop_flags: list[dict],
    weekly_totals: dict,
    period_start: str,
    get_week_fn,
) -> dict[str, list[dict]]:
    """
    Compute flags per employee.
    Returns {emp_id: [{code, severity, message}, ...]}
    """
    flags_by_emp: dict[str, list[dict]] = {}

    # Missing accrual
    emp_ids = set(df["emp_id"].astype(str))
    for eid in emp_ids:
        if eid not in accrual:
            if eid not in flags_by_emp:
                flags_by_emp[eid] = []
            flags_by_emp[eid].append({
                "code": "MISSING_ACCRUAL_RECORD",
                "severity": "HIGH",
                "message": "Employee not in accrual file",
            })

    # Leave exceeds bank / no banks but used leave (from leave suggestions)
    for s in leave_suggestions:
        eid = s["emp_id"]
        if eid not in flags_by_emp:
            flags_by_emp[eid] = []
        if s["proposed_code"] == "LWOP":
            # Could be NO_BANKS_BUT_USED_LEAVE or LEAVE_EXCEEDS_BANK
            if eid not in accrual:
                # Already flagged MISSING_ACCRUAL
                pass
            else:
                flags_by_emp[eid].append({
                    "code": "LEAVE_EXCEEDS_BANK",
                    "severity": "HIGH",
                    "message": f"Leave exceeds bank: {s['original_code']} → LWOP",
                })

    # NO_BANKS_BUT_USED_LEAVE: all banks 0 + leave used
    for eid in emp_ids:
        if eid not in accrual:
            continue
        bal = accrual[eid]
        total_banks = bal.get("SICK", 0) + bal.get("VAC", 0) + bal.get("AL", 0) + bal.get("COMP", 0)
        if total_banks == 0:
            emp_df = df[df["emp_id"] == eid]
            leave_used = 0
            for _, row in emp_df.iterrows():
                if code_draws_from_bank(str(row["code"])):
                    leave_used += float(row["hrs"])
            if leave_used > 0:
                if eid not in flags_by_emp:
                    flags_by_emp[eid] = []
                flags_by_emp[eid].append({
                    "code": "NO_BANKS_BUT_USED_LEAVE",
                    "severity": "HIGH",
                    "message": "All banks 0 but leave was used",
                })

    # LWOP_WITH_PREMIUM (from lwop_rules)
    for f in lwop_flags:
        eid = f["emp_id"]
        if eid not in flags_by_emp:
            flags_by_emp[eid] = []
        flags_by_emp[eid].append({
            "code": f["code"],
            "severity": f["severity"],
            "message": f.get("message", "LWOP with premium"),
        })

    # SICK_USED_WITH_OT15 (from sick_check - if we have sick suggestions, that implies this)
    sick_emp_ids = {s["emp_id"] for s in leave_suggestions}
    # Actually SICK_USED_WITH_OT15 is when effective sick > 0 and OT 1.5 exists - that's the sick_check rule output. We add a flag for it.
    # Per spec: SICK_USED_WITH_OT15 is medium. The sick_check produces suggestions. We could add a flag when that suggestion exists.
    # For simplicity, add flag when leave_suggestions include SICK→something AND we have OT1.5. Actually the sick_check already produces suggestions. The flag SICK_USED_WITH_OT15 could be added when sick_check produces a suggestion. Let me add that in pipeline when we have sick suggestions.

    # GUARANTEE_WITH_LWOP - from lwop_rules (guarantee→lwop suggestion). When we have that suggestion, add flag.
    # Already have LWOP rules producing suggestions. The flag GUARANTEE_WITH_LWOP could be added when that suggestion exists.

    # PAID_LT_40, PAID_PLUS_PREMIUM_GT_40, PAID_LOW_WITH_PREMIUM (per week)
    for eid, w in weekly_totals.items():
        if eid not in flags_by_emp:
            flags_by_emp[eid] = []
        for week_num, wk in [(1, w["week1"]), (2, w["week2"])]:
            paid = wk["paid"]
            premium = wk["premium"]
            if paid < 40 and (paid + premium) <= 40:
                flags_by_emp[eid].append({
                    "code": "PAID_LT_40",
                    "severity": "LOW",
                    "message": f"Week {week_num}: Paid < 40",
                })
            if (paid + premium) > 40:
                flags_by_emp[eid].append({
                    "code": "PAID_PLUS_PREMIUM_GT_40",
                    "severity": "LOW",
                    "message": f"Week {week_num}: Paid + Premium > 40",
                })
            if paid < 40 and premium > 0:
                flags_by_emp[eid].append({
                    "code": "PAID_LOW_WITH_PREMIUM",
                    "severity": "LOW",
                    "message": f"Week {week_num}: Paid < 40 but premium exists — verify missing time/coding.",
                })

    # Dedupe by (emp_id, code) - keep first
    for eid in flags_by_emp:
        seen = set()
        out = []
        for f in flags_by_emp[eid]:
            k = (f["code"], f.get("message", ""))
            if k not in seen:
                seen.add(k)
                out.append(f)
        flags_by_emp[eid] = out

    return flags_by_emp
