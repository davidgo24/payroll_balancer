"""
Rule 3 — LWOP minimal rules (MVP).
A) Flag LWOP_WITH_PREMIUM if LWOP and Premium exist in same week (high)
B) If LWOP exists due to leave exhaustion AND GUARANTEE exists: suggest GUARANTEE → LWOP (medium)
"""
import pandas as pd

from payroll_balancer.config.codes import LWOP_CODE, GUARANTEE_CODE, PREMIUM_CODES, is_premium


def lwop_rules(
    df: pd.DataFrame,
    leave_suggestions: list[dict],
    get_week_fn,
    period_start: str,
) -> tuple[list[dict], list[dict]]:
    """
    Returns (suggestions, flags).
    Suggestions: GUARANTEE → LWOP when LWOP used due to leave exhaustion and GUARANTEE exists.
    Flags: LWOP_WITH_PREMIUM per employee per week.
    """
    suggestions = []
    flags = []

    for emp_id, emp_df in df.groupby("emp_id"):
        # Build week sets: which weeks have LWOP, premium, guarantee
        weeks_with_lwop: set[int] = set()
        weeks_with_premium: set[int] = set()
        weeks_with_guarantee: set[int] = set()
        # Track if LWOP is due to leave exhaustion (from leave_check suggestions)
        lwop_suggested_weeks: set[int] = set()
        for s in leave_suggestions:
            if s["emp_id"] == emp_id and s["proposed_code"] == "LWOP":
                lwop_suggested_weeks.add(s["week"])

        for _, row in emp_df.iterrows():
            week = get_week_fn(str(row["date"]), period_start)
            code = str(row["code"]).strip()
            if code == LWOP_CODE:
                weeks_with_lwop.add(week)
            elif is_premium(code):
                weeks_with_premium.add(week)
            elif code == GUARANTEE_CODE:
                weeks_with_guarantee.add(week)

        # A) Flag LWOP_WITH_PREMIUM
        for w in weeks_with_lwop & weeks_with_premium:
            flags.append({
                "emp_id": emp_id,
                "week": w,
                "code": "LWOP_WITH_PREMIUM",
                "severity": "HIGH",
                "message": "LWOP and Premium in same week",
            })

        # B) GUARANTEE → LWOP when LWOP used (from leave exhaustion) and GUARANTEE exists
        # "LWOP exists due to leave exhaustion" = we have leave suggestions proposing LWOP for this emp
        lwop_from_exhaustion = bool(lwop_suggested_weeks)
        if lwop_from_exhaustion:
            for w in weeks_with_guarantee & (weeks_with_lwop | lwop_suggested_weeks):
                guarantee_rows = emp_df[
                    (emp_df["code"] == GUARANTEE_CODE) &
                    (emp_df.apply(lambda r: get_week_fn(str(r["date"]), period_start) == w, axis=1))
                ]
                for _, row in guarantee_rows.iterrows():
                    suggestions.append({
                        "emp_id": emp_id,
                        "date": row["date"],
                        "week": w,
                        "original_code": GUARANTEE_CODE,
                        "original_hrs": round(float(row["hrs"]), 2),
                        "proposed_code": LWOP_CODE,
                        "proposed_hrs": round(float(row["hrs"]), 2),
                        "reason": "LWOP used due to exhausted leave; guarantee cannot remain paid time (given, not earned).",
                        "severity": "MEDIUM",
                    })

    return suggestions, flags
