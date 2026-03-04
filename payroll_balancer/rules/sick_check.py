"""
Rule 2 — Sick overtime rule.
- When LWOP + sick: prioritize OT/CT EARN → REG FT (maximize paid credit before LWOP cap).
- When sick only (no LWOP): OT 1.5/CT EARN 1.5 → OT 1.0/CT EARN 1.0, capped at effective sick per week.
OT and CT EARN treated identically (both forms of premium OT pay).
"""
import pandas as pd

from payroll_balancer.config.codes import (
    BANK_DRAWS,
    REG_CODE,
    PREMIUM_15_TO_10,
    PREMIUM_OT_LIKE_CODES,
)


SICK_CODES = BANK_DRAWS["SICK"]


def sick_check(
    df: pd.DataFrame,
    leave_suggestions: list[dict],
    get_week_fn,
    period_start: str,
) -> list[dict]:
    """
    Rule 2: When LWOP + sick → OT 1.5/OT 1.0 → REG FT (maximize paid credit).
    When sick only → OT 1.5 → OT 1.0, capped at effective sick per week.
    """
    suggestions = []

    # Emps with LWOP suggestions (from leave exhaustion)
    emp_has_lwop = {s["emp_id"] for s in leave_suggestions if s.get("proposed_code") == "LWOP"}

    # Effective sick per emp per week
    sick_moved_per_emp_per_week: dict[str, dict[int, float]] = {}
    for s in leave_suggestions:
        if s["original_code"] in SICK_CODES:
            eid = s["emp_id"]
            w = s.get("week", 0)
            if eid not in sick_moved_per_emp_per_week:
                sick_moved_per_emp_per_week[eid] = {1: 0.0, 2: 0.0}
            if w in (1, 2):
                sick_moved_per_emp_per_week[eid][w] = sick_moved_per_emp_per_week[eid].get(w, 0) + s["proposed_hrs"]

    for emp_id, emp_df in df.groupby("emp_id"):
        original_sick_per_week: dict[int, float] = {1: 0.0, 2: 0.0}
        for _, row in emp_df.iterrows():
            if str(row["code"]).strip() in SICK_CODES:
                w = get_week_fn(str(row["date"]), period_start)
                if w in (1, 2):
                    original_sick_per_week[w] = original_sick_per_week.get(w, 0) + float(row["hrs"])

        moved = sick_moved_per_emp_per_week.get(emp_id, {1: 0.0, 2: 0.0})
        effective_sick_per_week = {
            w: max(0, original_sick_per_week.get(w, 0) - moved.get(w, 0))
            for w in (1, 2)
        }

        lwop_and_sick = emp_id in emp_has_lwop and any(effective_sick_per_week.get(w, 0) > 0 for w in (1, 2))

        if lwop_and_sick:
            # LWOP + sick: convert OT/CT EARN 1.5 and 1.0 → REG FT (same date); no cap
            for code in PREMIUM_OT_LIKE_CODES:
                rows = emp_df[emp_df["code"] == code].sort_values("date")
                for _, row in rows.iterrows():
                    week = get_week_fn(str(row["date"]), period_start)
                    if week not in (1, 2):
                        continue
                    hrs = round(float(row["hrs"]), 2)
                    if hrs <= 0:
                        continue
                    suggestions.append({
                        "emp_id": emp_id,
                        "date": row["date"],
                        "week": week,
                        "original_code": code,
                        "original_hrs": hrs,
                        "proposed_code": REG_CODE,
                        "proposed_hrs": hrs,
                        "reason": "LWOP used; convert OT to REG FT to maximize paid credit before LWOP cap",
                        "severity": "MEDIUM",
                    })
        else:
            # Sick only: OT 1.5/CT EARN 1.5 → OT 1.0/CT EARN 1.0, capped at effective sick per week
            cap_remaining = {1: effective_sick_per_week[1], 2: effective_sick_per_week[2]}

            for code_15, code_10 in PREMIUM_15_TO_10:
                rows_15 = emp_df[emp_df["code"] == code_15].sort_values("date")
                for _, row in rows_15.iterrows():
                    week = get_week_fn(str(row["date"]), period_start)
                    if week not in (1, 2) or cap_remaining[week] <= 0:
                        continue
                    hrs = float(row["hrs"])
                    eff_sick = effective_sick_per_week[week]
                    convert_hrs = min(hrs, cap_remaining[week])
                    if convert_hrs <= 0:
                        continue
                    cap_remaining[week] -= convert_hrs
                    suggestions.append({
                        "emp_id": emp_id,
                        "date": row["date"],
                        "week": week,
                        "original_code": code_15,
                        "original_hrs": round(hrs, 2),
                        "proposed_code": code_10,
                        "proposed_hrs": round(convert_hrs, 2),
                        "reason": f"Sick used this week (effective sick = {eff_sick:.2f} hrs)",
                        "severity": "MEDIUM",
                    })

    return suggestions
