# Payroll Balancer

Pre-validation layer for City of Montebello SMART transit bus operator payroll. Catches issues before New World and shows suggestions—**never mutates** original TCP hours.

## Tech Stack

| Layer       | Technology   |
|------------|---------------|
| Frontend   | React (Vite) |
| Backend    | Python FastAPI |
| Processing| pandas       |
| Persistence| SQLite       |

## Dev

```bash
# Backend (port 8001)
cd /Users/david/Payroll_Balancer
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn api.main:app --reload --port 8001

# Frontend (port 5173) — proxies /api to backend
cd frontend
npm install
npm run dev
```

Open http://localhost:5173

## MVP Features

- **Suggestions only** — grid always shows original TCP data
- **Period model** — biweekly Sun–Sat, user enters period end date
- **Append Week 2** — upload week 1 now, append week 2 later (reuse accrual)
- **Duplicate protection** — TCP file hash prevents re-import
- **Skip employees** — ADMIN LEAVE PAY excluded (finance handles)
- **Leave exhaustion** — period-scope fallback: SICK→VAC→COMP→AL→LWOP
- **Sick OT rule** — when sick used: suggest OT 1.5 → OT 1.0
- **LWOP rules** — flag LWOP+Premium; suggest GUARANTEE→LWOP when leave exhausted

## Inputs

- **TCP CSV**: No header. Columns (positional): `emp_id, hrs, code, date`. Date: M/D/YYYY or YYYY-MM-DD.
  - Example: `1020,8,REG FT,2/23/2026`
- **Accrual Excel**: AccrualBalanceReport.xlsx. Header row 1. Cols: Employee (emp_id), name, AL, COMP, HOLIDAY, SICK, VAC. Skips "Primary Department" rows. Negative balances treated as 0.

## Test with real data

Use your 2.22-2.28.26.csv (week 1) and AccrualBalanceReport.xlsx:

1. Start backend and frontend
2. Create new period — Period End Date: **2026-03-07** (Saturday)
3. Upload TCP CSV + Accrual Excel
4. Run — view employees, suggestions, flags

For append: upload week 2 CSV later with "Append Week 2" + select period 2026-03-07.

## Deploy to Railway

1. Push to GitHub and connect repo in [Railway](https://railway.app).
2. Add a **Volume** (Settings → Volumes) and set mount path to `/data`.
3. Add variable: `DATABASE_PATH=/data/payroll.db` (for persistent SQLite).
4. Deploy. Railway uses the Dockerfile and serves the app at the generated URL.

## Tests

```bash
python -m pytest tests/ -v
```
