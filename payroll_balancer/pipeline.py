"""
Pipeline — Rule 0 skip, then rules 1–3, totals, flags.
Never mutates original df. Outputs suggestions + context.
"""
import pandas as pd

from payroll_balancer.config.codes import SKIP_CODES, BANK_DRAWS, code_draws_from_bank
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
        original_grid = {
            "dates": dates_with_dow,
            "codes": pivot["codes"],
            "cells": pivot["cells"].get(emp_id, {}),
        }

        emp_suggestions = [s for s in all_suggestions if s["emp_id"] == emp_id]
        emp_flags = flags_by_emp.get(emp_id, [])
        flag_count = len(emp_flags)

        employees.append({"emp_id": emp_id, "name": name, "flagCount": flag_count})

        per_employee[emp_id] = {
            "originalGrid": original_grid,
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
