"""
Pipeline — Rule 0 skip, then rules 1–3, totals, flags.
Never mutates original df. Outputs suggestions + context.
"""
import pandas as pd

from payroll_balancer.config.codes import (
    SKIP_CODES,
    BANK_DRAWS,
    REG_LIKE_CODES,
    PREMIUM_CODES,
    LWOP_CODE,
    REG_CODE,
    OT_15_CODE,
    CT_EARN_15_CODE,
    OT_10_CODE,
    CT_EARN_10_CODE,
    code_draws_from_bank,
)
from payroll_balancer.rules.leave_check import leave_check
from payroll_balancer.rules.sick_check import sick_check
from payroll_balancer.rules.lwop_rules import lwop_rules
from payroll_balancer.totals import (
    compute_weekly_totals,
    compute_period_totals,
    compute_weekly_hints,
)
from payroll_balancer.flags import compute_flags


def run_pipeline(
    df: pd.DataFrame,
    accrual: dict,
    period_start: str,
    period_end: str,
    get_week_fn,
) -> dict:
    """
    Run full pipeline. Returns structure for API response.
    """
    # Rule 0 — Skip employees
    skip_mask = df["code"].astype(str).str.strip().isin(SKIP_CODES)
    skipped_emp_ids = set(df.loc[skip_mask, "emp_id"].astype(str))
    active_df = df[~df["emp_id"].astype(str).isin(skipped_emp_ids)].copy()

    skipped = []
    for eid in skipped_emp_ids:
        name = (accrual.get(eid) or {}).get("name", "") or eid
        reason = next((c for c in SKIP_CODES if c in df[df["emp_id"].astype(str) == eid]["code"].values), "ADMIN LEAVE PAY")
        skipped.append({"emp_id": eid, "name": name, "reason": reason})

    if active_df.empty:
        return {
            "periodId": period_end,
            "periodStart": period_start,
            "periodEnd": period_end,
            "employees": [],
            "skipped": skipped,
            "perEmployee": {},
        }

    # Rules 1–3
    leave_suggestions = leave_check(active_df, accrual, period_start, get_week_fn)
    sick_suggestions = sick_check(active_df, leave_suggestions, get_week_fn, period_start)
    lwop_suggestions, lwop_flag_list = lwop_rules(active_df, leave_suggestions, get_week_fn, period_start)

    all_suggestions = leave_suggestions + sick_suggestions + lwop_suggestions

    # Totals
    weekly_totals = compute_weekly_totals(active_df, period_start, get_week_fn)
    period_totals = compute_period_totals(weekly_totals)
    sick_codes = BANK_DRAWS.get("SICK", set())
    sick_moved_per_week: dict[str, dict[int, float]] = {}
    for s in leave_suggestions:
        if s["original_code"] in sick_codes:
            eid = str(s["emp_id"])
            w = s.get("week", 0)
            if eid not in sick_moved_per_week:
                sick_moved_per_week[eid] = {1: 0.0, 2: 0.0}
            if w in (1, 2):
                sick_moved_per_week[eid][w] = sick_moved_per_week[eid].get(w, 0) + s["proposed_hrs"]
    effective_sick_hrs_per_week: dict[str, dict[int, float]] = {}
    for emp_id, emp_df in active_df.groupby("emp_id"):
        eid = str(emp_id)
        effective_sick_hrs_per_week[eid] = {1: 0.0, 2: 0.0}
        for _, row in emp_df.iterrows():
            if str(row["code"]).strip() in sick_codes:
                w = get_week_fn(str(row["date"]), period_start)
                if w in (1, 2):
                    effective_sick_hrs_per_week[eid][w] += float(row["hrs"])
        moved = sick_moved_per_week.get(eid, {1: 0.0, 2: 0.0})
        for w in (1, 2):
            effective_sick_hrs_per_week[eid][w] = max(0, effective_sick_hrs_per_week[eid][w] - moved.get(w, 0))
    emp_has_lwop = {str(s["emp_id"]) for s in leave_suggestions if s.get("proposed_code") == "LWOP"}
    weekly_hints = compute_weekly_hints(weekly_totals, effective_sick_hrs_per_week, emp_has_lwop)

    # Flags
    flags_by_emp = compute_flags(
        active_df, accrual, leave_suggestions, lwop_flag_list, weekly_totals, period_start, get_week_fn
    )

    # Add flags when sick_check produced suggestions (once per emp)
    sick_flag_added = set()
    for s in sick_suggestions:
        eid = s["emp_id"]
        if eid in sick_flag_added:
            continue
        sick_flag_added.add(eid)
        if eid not in flags_by_emp:
            flags_by_emp[eid] = []
        if s.get("proposed_code") == "REG FT":
            flags_by_emp[eid].append({
                "code": "SICK_LWOP_OT_TO_REG",
                "severity": "MEDIUM",
                "message": "LWOP + sick — convert OT/CT EARN to REG FT to maximize paid credit",
            })
        else:
            flags_by_emp[eid].append({
                "code": "SICK_USED_WITH_OT15",
                "severity": "MEDIUM",
                "message": "Sick used with OT/CT EARN 1.5 — consider 1.5 → 1.0",
            })

    # Add GUARANTEE_WITH_LWOP when lwop_rules produced that suggestion
    for s in lwop_suggestions:
        if s.get("original_code") == "GUARANTEE":
            eid = s["emp_id"]
            if eid not in flags_by_emp:
                flags_by_emp[eid] = []
            flags_by_emp[eid].append({
                "code": "GUARANTEE_WITH_LWOP",
                "severity": "MEDIUM",
                "message": "Guarantee with LWOP — consider GUARANTEE → LWOP",
            })

    def _build_proposed_grid(original_cells, suggestions, dates_with_dow, original_codes):
        """Apply suggestions to original grid; return proposed {dates, codes, cells}.
        Suggestions only move the EXCESS — the portion covered by the bank stays as original code.
        E.g. 8.72 SICK with 7.32 bank → 7.32 stays SICK, 1.4 moves to VAC. Subtract proposed_hrs from
        original_code (the amount being reallocated), add to proposed_code.
        """
        import copy

        cells = copy.deepcopy(original_cells)
        new_codes: set[str] = set()

        for s in suggestions:
            date = str(s["date"])
            orig_code = s["original_code"]
            prop_code = s["proposed_code"]
            prop_hrs = s["proposed_hrs"]  # amount being moved (excess only)

            if date not in cells:
                cells[date] = {}
            if date in cells and orig_code in cells[date]:
                cells[date][orig_code] = round(cells[date][orig_code] - prop_hrs, 2)
                if cells[date][orig_code] <= 0:
                    del cells[date][orig_code]
            if not cells.get(date):
                cells[date] = {}

            cells[date][prop_code] = round(cells[date].get(prop_code, 0) + prop_hrs, 2)
            if prop_code not in original_codes:
                new_codes.add(prop_code)

        cells = {d: c for d, c in cells.items() if c}
        cells = _cap_documented_at_40(cells, period_start)
        cells, reg_cap_flag = _cap_reg_at_40(cells, period_start, original_cells)
        codes = sorted(set(original_codes) | new_codes | {c for cc in cells.values() for c in cc})
        return {"dates": dates_with_dow, "codes": codes, "cells": cells}, reg_cap_flag

    def _cap_documented_at_40(cells: dict, period_start: str) -> dict:
        """When a week's documented > 40, reduce LWOP (from end of week first) to cap at 40."""
        for week in (1, 2):
            dates_in_week = [d for d in cells if get_week_fn(d, period_start) == week]
            if not dates_in_week:
                continue
            paid = sum(
                float(hrs) for d, code_hrs in cells.items()
                for code, hrs in code_hrs.items()
                if get_week_fn(d, period_start) == week and code in REG_LIKE_CODES
            )
            premium = sum(
                float(hrs) for d, code_hrs in cells.items()
                for code, hrs in code_hrs.items()
                if get_week_fn(d, period_start) == week and code in PREMIUM_CODES
            )
            lwop = sum(
                float(hrs) for d, code_hrs in cells.items()
                for code, hrs in code_hrs.items()
                if get_week_fn(d, period_start) == week and code == LWOP_CODE
            )
            documented = round(paid + premium + lwop, 2)
            if documented <= 40:
                continue
            excess = round(documented - 40, 2)
            dates_with_lwop = sorted(
                [d for d in dates_in_week if cells.get(d, {}).get(LWOP_CODE, 0) > 0],
                reverse=True,
            )
            for date in dates_with_lwop:
                if excess <= 0:
                    break
                current = float(cells[date].get(LWOP_CODE, 0))
                reduce_by = round(min(excess, current), 2)
                if reduce_by <= 0:
                    continue
                cells[date][LWOP_CODE] = round(current - reduce_by, 2)
                if cells[date][LWOP_CODE] <= 0:
                    del cells[date][LWOP_CODE]
                excess -= reduce_by
        return {d: c for d, c in cells.items() if c}

    def _cap_reg_at_40(
        cells: dict, period_start: str, original_cells: dict
    ) -> tuple[dict, dict | None]:
        """Balance paid to 40 when paid+premium > 40.
        - paid > 40: convert REG FT → OT/CT 1.0 (reduce paid)
        - paid < 40: convert OT/CT 1.0 → REG FT (fill paid to 40)
        Heuristic for OT vs CT EARN: use whichever employee had more of (1.5) in original.
        Returns (cells, flag_or_none). Flag when cap applied — verify employee preference.
        """
        ot15 = sum(
            float(hrs) for code_hrs in original_cells.values()
            for code, hrs in code_hrs.items()
            if str(code).strip() == OT_15_CODE
        )
        ct15 = sum(
            float(hrs) for code_hrs in original_cells.values()
            for code, hrs in code_hrs.items()
            if str(code).strip() == CT_EARN_15_CODE
        )
        target_code = OT_10_CODE if ot15 >= ct15 else CT_EARN_10_CODE
        reg_cap_flag = None

        PREMIUM_10_CODES = (OT_10_CODE, CT_EARN_10_CODE)

        for week in (1, 2):
            paid = sum(
                float(hrs) for d, code_hrs in cells.items()
                for code, hrs in code_hrs.items()
                if get_week_fn(d, period_start) == week and code in REG_LIKE_CODES
            )
            premium = sum(
                float(hrs) for d, code_hrs in cells.items()
                for code, hrs in code_hrs.items()
                if get_week_fn(d, period_start) == week and code in PREMIUM_CODES
            )
            paid = round(paid, 2)
            premium = round(premium, 2)
            if round(paid + premium, 2) <= 40:
                continue

            # How much to move: when paid>40 reduce REG; when paid<40 fill from premium
            if paid > 40:
                amount_to_move = round(paid - 40, 2)
            else:
                amount_to_move = round((paid + premium) - 40, 2)  # unused in fill branch
            dates_in_week = sorted(
                [d for d in cells if get_week_fn(d, period_start) == week],
                reverse=True,
            )

            if paid > 40:
                # Reduce paid: REG FT → OT/CT 1.0 (move paid-40 from REG to premium)
                dates_with_reg = [d for d in dates_in_week if cells.get(d, {}).get(REG_CODE, 0) > 0]
                for date in dates_with_reg:
                    if amount_to_move <= 0:
                        break
                    current = float(cells[date].get(REG_CODE, 0))
                    reduce_by = round(min(amount_to_move, current), 2)
                    if reduce_by <= 0:
                        continue
                    cells[date][REG_CODE] = round(current - reduce_by, 2)
                    if cells[date][REG_CODE] <= 0:
                        del cells[date][REG_CODE]
                    cells[date][target_code] = round(cells[date].get(target_code, 0) + reduce_by, 2)
                    amount_to_move -= reduce_by
                    reg_cap_flag = {
                        "code": "REG_OT_CAP",
                        "severity": "MEDIUM",
                        "message": f"Excess REG converted to {target_code} — verify employee preference",
                    }
            else:
                # Fill paid to 40: OT/CT 1.0 → REG FT (take from 1.0x premium, end of week first)
                to_convert = round(min(40 - paid, premium), 2)
                if to_convert <= 0:
                    continue
                codes_to_try = [target_code] + [c for c in PREMIUM_10_CODES if c != target_code]
                for date in dates_in_week:
                    if to_convert <= 0:
                        break
                    for pcode in codes_to_try:
                        if cells.get(date, {}).get(pcode, 0) <= 0:
                            continue
                        current = float(cells[date].get(pcode, 0))
                        reduce_by = round(min(to_convert, current), 2)
                        if reduce_by <= 0:
                            continue
                        cells[date][pcode] = round(current - reduce_by, 2)
                        if cells[date][pcode] <= 0:
                            del cells[date][pcode]
                        cells[date][REG_CODE] = round(cells[date].get(REG_CODE, 0) + reduce_by, 2)
                        to_convert -= reduce_by
                        reg_cap_flag = {
                            "code": "REG_OT_CAP",
                            "severity": "MEDIUM",
                            "message": f"Premium {pcode} converted to REG FT to reach 40 — verify employee preference",
                        }
                        break

        return {d: c for d, c in cells.items() if c}, reg_cap_flag

    def _totals_from_proposed_grid(cells: dict, period_start: str) -> dict:
        """Compute weekly and period totals from proposed grid cells. Same structure as weekly/period totals."""
        w1 = {"paid": 0.0, "premium": 0.0, "lwop": 0.0, "documented": 0.0, "otOver40": 0.0}
        w2 = {"paid": 0.0, "premium": 0.0, "lwop": 0.0, "documented": 0.0, "otOver40": 0.0}
        for date, code_hrs in cells.items():
            week = get_week_fn(date, period_start)
            if week not in (1, 2):
                continue
            target = w1 if week == 1 else w2
            for code, hrs in code_hrs.items():
                code = str(code).strip()
                hrs = float(hrs)
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
        return {
            "week1": w1,
            "week2": w2,
            "period": {
                "paid": round(w1["paid"] + w2["paid"], 2),
                "premium": round(w1["premium"] + w2["premium"], 2),
                "lwop": round(w1["lwop"] + w2["lwop"], 2),
                "documented": round(w1["documented"] + w2["documented"], 2),
            },
        }

    # Bank snapshots per employee
    def _bank_snapshot(emp_id: str, emp_df: pd.DataFrame) -> dict:
        acc = accrual.get(emp_id) or {}
        banks = ["SICK", "VAC", "AL", "COMP"]
        acc_names = {"SICK": "SICK", "VAC": "VAC", "AL": "AL", "COMP": "COMP"}
        snapshot = {}
        for bank in banks:
            original = float(acc.get(acc_names[bank], 0))
            used = emp_df[emp_df["code"].apply(lambda c: code_draws_from_bank(str(c).strip()) == bank)]["hrs"].sum()
            used = round(used, 2)
            remaining = round(original - used, 2)
            snapshot[bank] = {"original": original, "used": used, "remaining": remaining}
        if acc.get("HOLIDAY") is not None:
            snapshot["HOLIDAY"] = {"original": float(acc["HOLIDAY"]), "used": 0, "remaining": float(acc["HOLIDAY"])}
        return snapshot

    # Build per-employee results
    from payroll_balancer.pivot import pivot_to_grid, add_day_of_week, format_date_ui

    employees = []
    per_employee = {}

    for emp_id in active_df["emp_id"].astype(str).unique():
        emp_df = active_df[active_df["emp_id"].astype(str) == emp_id]
        name = (accrual.get(emp_id) or {}).get("name", "") or emp_id

        bank_snapshot = _bank_snapshot(emp_id, emp_df)

        pivot = pivot_to_grid(emp_df)
        dates_with_dow = add_day_of_week(pivot["dates"])
        original_cells = pivot["cells"].get(emp_id, {})
        original_grid = {
            "dates": dates_with_dow,
            "codes": pivot["codes"],
            "cells": original_cells,
        }

        emp_suggestions = [s for s in all_suggestions if s["emp_id"] == emp_id]
        emp_flags = flags_by_emp.get(emp_id, [])
        flag_count = len(emp_flags)

        # Proposed grid: apply suggestions to get resulting hours by date and code
        proposed_grid = None
        proposed_totals = None
        if emp_suggestions:
            proposed_grid, reg_cap_flag = _build_proposed_grid(
                original_cells, emp_suggestions, dates_with_dow, pivot["codes"]
            )
            proposed_totals = _totals_from_proposed_grid(proposed_grid["cells"], period_start)
            if reg_cap_flag:
                emp_flags = list(emp_flags) + [reg_cap_flag]

        employees.append({"emp_id": emp_id, "name": name, "flagCount": flag_count})

        per_employee[emp_id] = {
            "originalGrid": original_grid,
            "proposedGrid": proposed_grid,
            "proposedTotals": proposed_totals,
            "bankSnapshot": bank_snapshot,
            "suggestions": emp_suggestions,
            "weeklyTotals": weekly_totals.get(emp_id, {"week1": {}, "week2": {}}),
            "periodTotals": period_totals.get(emp_id, {}),
            "weeklyHints": weekly_hints.get(emp_id, []),
            "flags": emp_flags,
        }

    return {
        "periodId": period_end,
        "periodStart": period_start,
        "periodEnd": period_end,
        "employees": employees,
        "skipped": skipped,
        "perEmployee": per_employee,
    }
