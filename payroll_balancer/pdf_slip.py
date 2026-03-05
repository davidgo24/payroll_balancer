"""
Time Exception Slip PDF generation.
Port of logic from time-exception-slip-tool (https://github.com/davidgo24/time-exception-slip-tool).
Requires OT_Time_Exception_Slip_Sample.pdf in api/ or project root — copy from that repo.
"""
import io
import logging
from pathlib import Path

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from PyPDF2 import PdfReader, PdfWriter

logging.getLogger("PyPDF2").setLevel(logging.CRITICAL)

# Code mapping: Payroll Balancer code -> time-exception-slip-tool category
CODE_TO_OT_CATEGORY = {
    "OT 1.0": "ot10",
    "OT 1.5": "ot15",
    "CT EARN 1.0": "cte10",
    "CT EARN 1.5": "cte15",
}

DATE_FMT_OUTPUT = "%m-%d-%y"
DEPT_CODE = "910"
PAGE_W, PAGE_H = letter

# Field coordinates from time-exception-slip-tool (x, y, w, h, font_size, align)
FIELD_COORDS = {
    "Employee Name": (99.00, 711.72, 201.60, 16.92, 11, "left"),
    "Dept": (345.84, 711.72, 45.60, 16.92, 11, "center"),
    "Ending Date": (459.24, 711.72, 104.76, 16.92, 10, "left"),
    "Employee": (76.32, 681.36, 65.52, 16.92, 10, "left"),
    "Dates 1_2": (18.48, 365.16, 80.76, 16.92, 7, "left"),
    "Dates 2_2": (18.48, 347.04, 80.76, 16.92, 7, "left"),
    "Dates 3_2": (18.48, 328.92, 80.76, 16.92, 7, "left"),
    "Dates 4_2": (18.48, 310.80, 80.76, 16.92, 7, "left"),
    "Dates 5_2": (18.48, 292.68, 80.76, 16.92, 7, "left"),
    "OT1": (143.64, 366.78, 18.33, 15.30, 7, "center"),
    "OT2": (143.64, 348.66, 18.33, 15.30, 7, "center"),
    "OT3": (143.64, 330.54, 18.33, 15.30, 7, "center"),
    "OT4": (143.64, 312.42, 18.33, 15.30, 7, "center"),
    "OT5": (143.64, 294.30, 18.33, 15.30, 7, "center"),
    "OT6": (143.64, 275.58, 18.33, 15.30, 7, "center"),
    "OTH1": (166.31, 366.78, 18.33, 15.30, 7, "center"),
    "OTH2": (166.31, 348.66, 18.33, 15.30, 7, "center"),
    "OTH3": (166.31, 330.54, 18.33, 15.30, 7, "center"),
    "OTH4": (166.31, 312.42, 18.33, 15.30, 7, "center"),
    "OTH5": (166.31, 294.30, 18.33, 15.30, 7, "center"),
    "OTH6": (166.31, 275.58, 18.33, 15.30, 7, "center"),
    "CTE1": (189.05, 366.78, 18.33, 15.30, 7, "center"),
    "CTE2": (189.05, 348.66, 18.33, 15.30, 7, "center"),
    "CTE3": (189.05, 330.54, 18.33, 15.30, 7, "center"),
    "CTE4": (189.05, 312.42, 18.33, 15.30, 7, "center"),
    "CTE5": (189.05, 294.30, 18.33, 15.30, 7, "center"),
    "CTE6": (189.05, 275.58, 18.33, 15.30, 7, "center"),
    "CTEH1": (211.98, 366.78, 18.33, 15.30, 7, "center"),
    "CTEH2": (211.98, 348.66, 18.33, 15.30, 7, "center"),
    "CTEH3": (211.98, 330.54, 18.33, 15.30, 7, "center"),
    "CTEH4": (211.98, 312.42, 18.33, 15.30, 7, "center"),
    "CTEH5": (211.98, 294.30, 18.33, 15.30, 7, "center"),
    "CTEH6": (211.98, 275.58, 18.33, 15.30, 7, "center"),
    "HTOT1": (302.43, 275.58, 18.33, 15.30, 7, "center"),
}

OT_ROW_FIELDS = {
    "dates": ["Dates 1_2", "Dates 2_2", "Dates 3_2", "Dates 4_2", "Dates 5_2"],
    "ot10": ["OT1", "OT2", "OT3", "OT4", "OT5"],
    "ot15": ["OTH1", "OTH2", "OTH3", "OTH4", "OTH5"],
    "cte10": ["CTE1", "CTE2", "CTE3", "CTE4", "CTE5"],
    "cte15": ["CTEH1", "CTEH2", "CTEH3", "CTEH4", "CTEH5"],
}

OT_TOTAL_FIELDS = {
    "ot10": "OT6",
    "ot15": "OTH6",
    "cte10": "CTE6",
    "cte15": "CTEH6",
}

HOURS_TOTAL_FIELD = "HTOT1"


def _parse_date(s: str):
    from datetime import datetime
    s = str(s).strip()
    # Strip ISO time suffix if present (e.g. "2026-02-23T00:00:00.000Z")
    if "T" in s:
        s = s.split("T")[0]
    # Numeric timestamp (ms) — only if string looks like one
    if s.replace(".", "").isdigit():
        try:
            ts = float(s)
            if ts > 1e12:  # milliseconds
                ts = ts / 1000
            return datetime.utcfromtimestamp(ts)
        except (ValueError, TypeError, OSError):
            pass
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m-%d-%Y", "%m/%d/%y", "%m-%d-%y"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    raise ValueError(f"Cannot parse date: {s}")


def _pay_period_weeks(ending_date_str: str):
    from datetime import timedelta
    end = _parse_date(ending_date_str)
    wk1_start = end - timedelta(days=13)
    wk1_end = end - timedelta(days=7)
    wk2_start = end - timedelta(days=6)
    wk2_end = end
    return (wk1_start, wk1_end), (wk2_start, wk2_end)


def _format_date_short(dt) -> str:
    return f"{dt.month}/{dt.day}"


def _fmt_hours(h: float) -> str:
    return f"{round(h, 2):.2f}"


def _aggregate_ot_by_week(ot_entries: list, wk1_start, wk1_end, wk2_start, wk2_end) -> list:
    weeks = [
        {"ot10": 0.0, "ot15": 0.0, "cte10": 0.0, "cte15": 0.0, "dates": set(), "has_data": False, "row_total": 0.0},
        {"ot10": 0.0, "ot15": 0.0, "cte10": 0.0, "cte15": 0.0, "dates": set(), "has_data": False, "row_total": 0.0},
    ]
    for entry in ot_entries:
        try:
            dt = _parse_date(entry["date"])
        except ValueError:
            continue
        cat = entry.get("category", "")
        hours = round(float(entry.get("hours", 0)), 2)
        if hours <= 0 or cat not in ("ot10", "ot15", "cte10", "cte15"):
            continue
        if wk1_start <= dt <= wk1_end:
            week = weeks[0]
        elif wk2_start <= dt <= wk2_end:
            week = weeks[1]
        else:
            continue
        week[cat] += hours
        week["dates"].add(dt)
        week["has_data"] = True
        week["row_total"] += hours
    for w in weeks:
        sorted_dates = sorted(w["dates"])
        w["dates_str"] = ", ".join(_format_date_short(d) for d in sorted_dates)
    return weeks


def grid_cells_to_ot_entries(cells: dict, dates_list: list = None, period_start: str = ""):
    """
    Convert Payroll Balancer grid cells to ot_data.entries format.
    Only includes OT 1.0, OT 1.5, CT EARN 1.0, CT EARN 1.5 — nothing else.
    cells: { date: { code: hrs } }
    Returns entries: [{ date, category: ot10|ot15|cte10|cte15, hours }]
    Merges by (date, category) to avoid double-counting if date keys vary (e.g. 2026-02-22 vs 2/22/2026).
    """
    merged: dict[tuple, float] = {}
    for date_str, code_hrs in cells.items():
        for code, hrs in code_hrs.items():
            code = str(code).strip()
            cat = CODE_TO_OT_CATEGORY.get(code)
            if not cat or float(hrs or 0) <= 0:
                continue
            try:
                dt = _parse_date(date_str)
                norm_date = dt.strftime("%Y-%m-%d")
            except ValueError:
                norm_date = str(date_str)
            key = (norm_date, cat)
            merged[key] = merged.get(key, 0.0) + float(hrs)
    return [
        {"date": k[0], "category": k[1], "hours": round(v, 2)}
        for k, v in merged.items()
    ]


def _create_overlay(values: dict) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    for field_name, text in values.items():
        if not text or field_name not in FIELD_COORDS:
            continue
        x, y, w, h, font_size, align = FIELD_COORDS[field_name]
        c.setFont("Helvetica", font_size)
        text_y = y + (h - font_size) / 2 + 1
        if align == "center":
            text_x = x + w / 2
            c.drawCentredString(text_x, text_y, str(text))
        else:
            text_x = x + 2
            c.drawString(text_x, text_y, str(text))
    c.save()
    return buf.getvalue()


def fill_single_pdf(
    employee: dict,
    pp_end: str,
    template_bytes: bytes,
    ot_entries: list | None = None,
) -> bytes:
    """Fill a single Time Exception Slip PDF."""
    last = employee.get("last") or employee.get("last_name") or ""
    first = employee.get("first") or employee.get("first_name") or ""
    emp_no = str(employee.get("emp_no") or employee.get("emp_id") or "")
    combined_name = f"{last}, {first}".strip(", ").strip() or (employee.get("name") or emp_no)
    end_dt = _parse_date(pp_end)
    pp_end_formatted = end_dt.strftime(DATE_FMT_OUTPUT)

    values = {
        "Employee Name": combined_name,
        "Dept": DEPT_CODE,
        "Ending Date": pp_end_formatted,
        "Employee": emp_no,
    }

    if ot_entries:
        (wk1_start, wk1_end), (wk2_start, wk2_end) = _pay_period_weeks(pp_end)
        weeks = _aggregate_ot_by_week(ot_entries, wk1_start, wk1_end, wk2_start, wk2_end)
        for week_idx, week in enumerate(weeks):
            if not week["has_data"]:
                continue
            values[OT_ROW_FIELDS["dates"][week_idx]] = week["dates_str"]
            for cat_key in ("ot10", "ot15", "cte10", "cte15"):
                hrs = week[cat_key]
                if hrs > 0:
                    values[OT_ROW_FIELDS[cat_key][week_idx]] = _fmt_hours(hrs)
        # Per-category totals and grand total — derive HTOT1 from category sums (single source of truth)
        cat_totals = {k: sum(w[k] for w in weeks) for k in ("ot10", "ot15", "cte10", "cte15")}
        for cat_key in ("ot10", "ot15", "cte10", "cte15"):
            if cat_totals[cat_key] > 0:
                values[OT_TOTAL_FIELDS[cat_key]] = _fmt_hours(cat_totals[cat_key])
        grand_total = sum(cat_totals.values())
        if grand_total > 0:
            values[HOURS_TOTAL_FIELD] = _fmt_hours(grand_total)

    overlay_bytes = _create_overlay(values)
    template_reader = PdfReader(io.BytesIO(template_bytes))
    overlay_reader = PdfReader(io.BytesIO(overlay_bytes))
    template_page = template_reader.pages[0]
    overlay_page = overlay_reader.pages[0]
    template_page.merge_page(overlay_page)
    if "/Annots" in template_page:
        del template_page["/Annots"]
    writer = PdfWriter()
    writer.add_page(template_page)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def merge_pdfs(pdf_bytes_list: list[bytes]) -> bytes:
    writer = PdfWriter()
    for pdf_bytes in pdf_bytes_list:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        writer.add_page(reader.pages[0])
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def get_template_path() -> Path | None:
    """Locate OT_Time_Exception_Slip_Sample.pdf."""
    base = Path(__file__).parent.parent
    candidates = [
        base / "api" / "OT_Time_Exception_Slip_Sample.pdf",
        base / "OT_Time_Exception_Slip_Sample.pdf",
    ]
    for p in candidates:
        if p.exists():
            return p
    return None
