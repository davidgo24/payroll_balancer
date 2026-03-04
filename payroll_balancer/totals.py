"""
Totals engine — weekly + period.
Paid (REG-like), Premium, LWOP, Documented Total, OT Over 40.
"""
import pandas as pd

from payroll_balancer.config.codes import REG_LIKE_CODES, PREMIUM_CODES, LWOP_CODE


def compute_weekly_totals(
    df: pd.DataFrame,
    period_start: str,
    get_week_fn,
) -> dict[str, dict]:
    """
    Compute per-employee weekly totals for week 1 and week 2.
    Returns {emp_id: {week1: {paid, premium, lwop, documented, otOver40}, week2: {...}}}
    """
    result: dict = {}

    for emp_id, emp_df in df.groupby("emp_id"):
        w1 = {"paid": 0.0, "premium": 0.0, "lwop": 0.0, "documented": 0.0, "otOver40": 0.0}
        w2 = {"paid": 0.0, "premium": 0.0, "lwop": 0.0, "documented": 0.0, "otOver40": 0.0}

        for _, row in emp_df.iterrows():
            week = get_week_fn(str(row["date"]), period_start)
            hrs = float(row["hrs"])
            code = str(row["code"]).strip()

            target = w1 if week == 1 else w2
            if week not in (1, 2):
                continue

            if code in REG_LIKE_CODES:
                target["paid"] += hrs
            elif code in PREMIUM_CODES:
                target["premium"] += hrs
            elif code == LWOP_CODE:
                target["lwop"] += hrs

        for w in (w1, w2):
            w["documented"] = round(w["paid"] + w["premium"] + w["lwop"], 2)
            over40 = (w["paid"] + w["premium"]) - 40
            w["otOver40"] = round(max(0, over40), 2)
            w["paid"] = round(w["paid"], 2)
            w["premium"] = round(w["premium"], 2)
            w["lwop"] = round(w["lwop"], 2)

        result[emp_id] = {"week1": w1, "week2": w2}

    return result


def compute_period_totals(weekly: dict) -> dict[str, dict]:
    """
    Sum week1 + week2 for period totals.
    Returns {emp_id: {paid, premium, lwop, documented}}
    """
    result = {}
    for emp_id, w in weekly.items():
        w1, w2 = w["week1"], w["week2"]
        result[emp_id] = {
            "paid": round(w1["paid"] + w2["paid"], 2),
            "premium": round(w1["premium"] + w2["premium"], 2),
            "lwop": round(w1["lwop"] + w2["lwop"], 2),
            "documented": round(w1["documented"] + w2["documented"], 2),
        }
    return result


def compute_weekly_hints(
    weekly: dict,
    effective_sick_hrs_per_week: dict[str, dict[int, float]] | None = None,
    emp_has_lwop: set | None = None,
) -> dict[str, list[dict]]:
    """
    If Documented != 40 or Regular Hrs != 40, add hint message.
    effective_sick_hrs_per_week: {emp_id: {1: float, 2: float}} — sick hrs that stayed.
    emp_has_lwop: set of emp_ids with LWOP suggestions — when LWOP+sick, suggest OT→REG FT.
    Returns {emp_id: [{week, message}, ...]}
    """
    result: dict[str, list] = {}
    emp_has_lwop = emp_has_lwop or set()
    for emp_id, w in weekly.items():
        hints = []
        sick_hrs = (effective_sick_hrs_per_week or {}).get(emp_id, {})
        lwop_and_sick = emp_id in emp_has_lwop and any(sick_hrs.get(i, 0) > 0 for i in (1, 2))
        for i, wk in enumerate([w["week1"], w["week2"]], 1):
            paid = wk["paid"]
            doc = wk["documented"]
            prefix = f"Week {i}: "
            if doc < 40:
                diff = 40 - doc
                hints.append({"week": i, "message": f"{prefix}Documented total is {doc:.2f}. Add {diff:.2f} hrs (LWOP) to reach 40."})
            elif paid > 40:
                excess_reg = round(paid - 40, 2)
                sick_hrs_week = sick_hrs.get(i, 0) or 0
                if lwop_and_sick and sick_hrs_week > 0:
                    hints.append({"week": i, "message": f"{prefix}Regular Hrs is {paid:.2f} ({excess_reg:.2f} over 40). Convert {excess_reg:.2f} hrs to REG FT (LWOP used; maximize paid credit before LWOP cap)."})
                elif sick_hrs_week > 0:
                    ot10_hrs = round(min(excess_reg, sick_hrs_week), 2)
                    ot15_hrs = round(max(0, excess_reg - sick_hrs_week), 2)
                    if ot15_hrs > 0:
                        hints.append({"week": i, "message": f"{prefix}Regular Hrs is {paid:.2f} ({excess_reg:.2f} over 40). Convert {ot10_hrs:.2f} hrs to OT/CT EARN 1.0 (sick used), {ot15_hrs:.2f} hrs to 1.5."})
                    else:
                        hints.append({"week": i, "message": f"{prefix}Regular Hrs is {paid:.2f} ({excess_reg:.2f} over 40). Convert {ot10_hrs:.2f} hrs to OT/CT EARN 1.0 (sick used)."})
                else:
                    hints.append({"week": i, "message": f"{prefix}Regular Hrs is {paid:.2f} ({excess_reg:.2f} over 40). Convert {excess_reg:.2f} hrs to OT/CT EARN 1.5."})
            elif doc > 40:
                diff = round(doc - 40, 2)
                hints.append({"week": i, "message": f"{prefix}Documented total is {doc:.2f} ({diff:.2f} over 40). Review excess Premium/LWOP allocation."})
        result[emp_id] = hints
    return result
