"""
FastAPI — POST /api/run for create and append.
"""
import json
from pathlib import Path

from fastapi import FastAPI, File, Form, UploadFile, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

# Add project root to path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from payroll_balancer.loaders import load_tcp_csv, load_accrual_excel
from payroll_balancer.week_split import period_end_to_start, is_saturday, get_week_number
from payroll_balancer.db import (
    init_db,
    create_period,
    get_period,
    list_period_ids,
    get_tcp_hashes,
    add_tcp_hash,
    is_duplicate_tcp,
    update_accrual_snapshot,
    insert_hours,
    get_hours,
    get_accrual_snapshot,
)
from payroll_balancer.pipeline import run_pipeline


app = FastAPI(title="Payroll Balancer")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    init_db()


def get_week_fn(date_str: str, period_start: str) -> int:
    return get_week_number(date_str, period_start)


@app.get("/api/periods")
async def list_periods():
    """List period IDs for append mode dropdown."""
    return {"periodIds": list_period_ids()}


@app.get("/api/run")
async def get_run(period_id: str = Query(...)):
    """Load results for an existing period (no upload). View runs from terminal or prior uploads."""
    period = get_period(period_id)
    if not period:
        raise HTTPException(404, f"Period {period_id} not found")
    accrual = get_accrual_snapshot(period_id)
    if not accrual:
        raise HTTPException(400, "No accrual snapshot for this period")
    all_hours = get_hours(period_id)
    if not all_hours:
        raise HTTPException(400, "No hours data for this period")
    import pandas as pd
    df_full = pd.DataFrame(all_hours)
    result = run_pipeline(
        df_full,
        accrual,
        period["start_date"],
        period["end_date"],
        get_week_fn,
    )
    return result


@app.post("/api/run")
async def run(
    tcp_file: UploadFile = File(...),
    accrual_file: UploadFile = File(None),
    period_end_date: str = Form(None),
    append: str = Form("false"),
    period_id: str = Form(None),
    reuse_accrual: str = Form("true"),
):
    """
    Create new period or append week 2.
    - Create: tcp_file, accrual_file, period_end_date required
    - Append: tcp_file, period_id required; accrual_file optional if reuse_accrual
    """
    tcp_content = await tcp_file.read()
    is_append = str(append).lower() == "true"
    reuse_accrual_val = str(reuse_accrual).lower() == "true"

    if is_append:
        if not period_id:
            raise HTTPException(400, "period_id required when append=true")
        period = get_period(period_id)
        if not period:
            raise HTTPException(404, f"Period {period_id} not found")

        if is_duplicate_tcp(period_id, load_tcp_csv(tcp_content)[1]):
            raise HTTPException(400, "Duplicate TCP file — already uploaded for this period")

        accrual = get_accrual_snapshot(period_id)
        if not accrual and (not accrual_file or not reuse_accrual_val):
            raise HTTPException(400, "Accrual required: no stored snapshot and no file uploaded")

        if accrual_file and not reuse_accrual_val:
            acc_content = await accrual_file.read()
            accrual = load_accrual_excel(acc_content)
            update_accrual_snapshot(period_id, json.dumps(accrual))

        period_start = period["start_date"]
        period_end = period["end_date"]

        df, file_hash = load_tcp_csv(tcp_content)
        # Filter to dates within period
        df = df[(df["date"] >= period_start) & (df["date"] <= period_end)]
        if df.empty:
            raise HTTPException(400, "No hours in TCP file fall within this period")

        rows = df.to_dict("records")
        for r in rows:
            r["emp_id"] = str(r["emp_id"])
        insert_hours(period_id, rows)
        add_tcp_hash(period_id, file_hash)

        # Load all hours for period
        all_hours = get_hours(period_id)
        import pandas as pd
        df_full = pd.DataFrame(all_hours)

    else:
        if not period_end_date:
            raise HTTPException(400, "period_end_date required when append=false")
        if not accrual_file:
            raise HTTPException(400, "accrual_file required when creating new period")

        if not is_saturday(period_end_date):
            # Allow but could add warning in response
            pass

        period_start = period_end_to_start(period_end_date)
        period_id = period_end_date

        accrual_content = await accrual_file.read()
        accrual = load_accrual_excel(accrual_content)

        if not create_period(period_id, period_start, period_end_date, json.dumps(accrual)):
            raise HTTPException(400, f"Period {period_id} already exists")

        df, file_hash = load_tcp_csv(tcp_content)
        df = df[(df["date"] >= period_start) & (df["date"] <= period_end_date)]
        if df.empty:
            raise HTTPException(400, "No hours in TCP file fall within this period")

        rows = df.to_dict("records")
        for r in rows:
            r["emp_id"] = str(r["emp_id"])
        insert_hours(period_id, rows)
        add_tcp_hash(period_id, file_hash)
        df_full = df

    result = run_pipeline(
        df_full,
        accrual,
        period_start,
        period_id,
        get_week_fn,
    )
    return result
