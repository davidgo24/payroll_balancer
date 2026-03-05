import { useState, useMemo, useCallback } from 'react'

const SEVERITY_ORDER = { HIGH: 0, MEDIUM: 1, LOW: 2 }

export default function ResultsScreen({ result, onReset }) {
  const [selectedEmp, setSelectedEmp] = useState(null)
  const [filterFlag, setFilterFlag] = useState('')
  const [showOnlyFlagged, setShowOnlyFlagged] = useState(false)
  const [search, setSearch] = useState('')
  const [finalizedGrids, setFinalizedGrids] = useState({})
  const [generatingSlips, setGeneratingSlips] = useState(false)

  const employees = result.employees || []
  const perEmployee = result.perEmployee || {}
  const skipped = result.skipped || []
  const needsReview = result.needsReview || []

  const filteredEmps = useMemo(() => {
    let list = employees
    if (showOnlyFlagged) list = list.filter((e) => e.flagCount > 0)
    if (filterFlag) list = list.filter((e) => (perEmployee[e.emp_id]?.flags || []).some((f) => f.code === filterFlag))
    if (search.trim()) {
      const q = search.toLowerCase()
      list = list.filter((e) => e.name?.toLowerCase().includes(q) || e.emp_id?.includes(q))
    }
    return [...list].sort((a, b) => (a.flagCount || 0) - (b.flagCount || 0)).reverse()
  }, [employees, showOnlyFlagged, filterFlag, search, perEmployee])

  const emp = selectedEmp && perEmployee[selectedEmp] ? perEmployee[selectedEmp] : null
  const selectedEmpInfo = employees.find((e) => e.emp_id === selectedEmp)

  const allFlags = useMemo(() => {
    const set = new Set()
    employees.forEach((e) => (perEmployee[e.emp_id]?.flags || []).forEach((f) => set.add(f.code)))
    return [...set]
  }, [employees, perEmployee])

  const sourceForFinalized = emp?.proposedGrid || emp?.originalGrid
  const finalizedGrid = selectedEmp ? finalizedGrids[selectedEmp] : null
  const effectiveFinalized = finalizedGrid || sourceForFinalized

  const handleCopyFromProposed = useCallback(() => {
    if (!selectedEmp || !emp?.proposedGrid) return
    setFinalizedGrids((prev) => ({
      ...prev,
      [selectedEmp]: JSON.parse(JSON.stringify(emp.proposedGrid)),
    }))
  }, [selectedEmp, emp?.proposedGrid])

  const handleCopyFromProposedForAll = useCallback(() => {
    const next = {}
    employees.forEach((e) => {
      const g = perEmployee[e.emp_id]?.proposedGrid || perEmployee[e.emp_id]?.originalGrid
      if (g) next[e.emp_id] = JSON.parse(JSON.stringify(g))
    })
    setFinalizedGrids(next)
  }, [employees, perEmployee])

  const handleCellChange = useCallback((date, code, value) => {
    if (!selectedEmp) return
    const src = finalizedGrids[selectedEmp] || perEmployee[selectedEmp]?.proposedGrid || perEmployee[selectedEmp]?.originalGrid
    const g = src ? JSON.parse(JSON.stringify(src)) : { dates: [], codes: [], cells: {} }
    if (!g.cells) g.cells = {}
    if (!g.cells[date]) g.cells[date] = {}
    const num = parseFloat(value)
    if (!Number.isNaN(num) && num !== 0) {
      g.cells[date][code] = num
    } else {
      delete g.cells[date][code]
      if (Object.keys(g.cells[date]).length === 0) delete g.cells[date]
    }
    setFinalizedGrids((prev) => ({ ...prev, [selectedEmp]: g }))
  }, [selectedEmp, perEmployee, finalizedGrids])

  const handleGenerateSlips = useCallback(async () => {
    setGeneratingSlips(true)
    try {
      const effectiveGrids = {}
      employees.forEach((e) => {
        const grid = finalizedGrids[e.emp_id] || perEmployee[e.emp_id]?.proposedGrid || perEmployee[e.emp_id]?.originalGrid
        if (grid) effectiveGrids[e.emp_id] = grid
      })
      const res = await fetch('/api/generate-slips', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          periodEnd: result.periodEnd,
          periodStart: result.periodStart,
          employees,
          finalizedGrids: effectiveGrids,
        }),
      })
      if (!res.ok) {
        const err = await res.json().catch(() => null)
        const msg = err?.detail || err?.error || res.statusText || 'Failed to generate PDFs'
        throw new Error(Array.isArray(msg) ? msg.join('; ') : String(msg))
      }
      const blob = await res.blob()
      const a = document.createElement('a')
      a.href = URL.createObjectURL(blob)
      const cd = res.headers.get('Content-Disposition')
      const match = cd && cd.match(/filename="?([^";]+)"?/)
      a.download = match ? match[1] : `Time_Exception_Slips_${result.periodEnd}.pdf`
      a.click()
      URL.revokeObjectURL(a.href)
    } catch (err) {
      alert(err.message || 'Failed to generate slips')
    } finally {
      setGeneratingSlips(false)
    }
  }, [result.periodEnd, result.periodStart, employees, finalizedGrids, perEmployee])

  return (
    <section className="results-screen">
      <header className="results-header">
        <h2>Payroll Balancer</h2>
        <p className="period-range">
          {result.periodStart} – {result.periodEnd}
        </p>
        <div className="header-actions">
          <button
            type="button"
            className="btn-copy-all"
            onClick={handleCopyFromProposedForAll}
            disabled={employees.length === 0}
          >
            Copy Proposed → Finalized (all)
          </button>
          <button
            type="button"
            className="btn-generate-slips"
            onClick={handleGenerateSlips}
            disabled={generatingSlips || employees.length === 0}
          >
            {generatingSlips ? 'Generating…' : 'Generate time exception slips'}
          </button>
          <button type="button" className="btn-reset" onClick={onReset}>
            New run
          </button>
        </div>
      </header>

      {skipped.length > 0 && (
        <div className="skipped-banner">
          Skipped ({skipped.length}): {skipped.map((s) => `${s.emp_id} ${s.name}`).join(', ')} — {skipped[0]?.reason || 'finance handles'}
        </div>
      )}

      {needsReview.length > 0 && (
        <div className="needs-review-banner">
          <h4>Needs review ({needsReview.length})</h4>
          <p className="needs-review-hint">Proposed totals not at 40 — tap to jump</p>
          <ul className="needs-review-list">
            {needsReview.map((r) => (
              <li key={r.emp_id} onClick={() => setSelectedEmp(r.emp_id)}>
                <span className="emp-id">{r.emp_id}</span>
                <span className="emp-name">{r.name}</span>
                <span className="reason">{r.reason}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="results-body">
        <aside className="employee-sidebar">
          <div className="filters">
            <input
              type="search"
              placeholder="Search..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
            <label>
              <input type="checkbox" checked={showOnlyFlagged} onChange={(e) => setShowOnlyFlagged(e.target.checked)} />
              Flagged only
            </label>
            <select value={filterFlag} onChange={(e) => setFilterFlag(e.target.value)}>
              <option value="">All flags</option>
              {allFlags.map((f) => (
                <option key={f} value={f}>{f}</option>
              ))}
            </select>
          </div>
          <ul className="employee-list">
            {filteredEmps.map((e) => (
              <li
                key={e.emp_id}
                className={selectedEmp === e.emp_id ? 'selected' : ''}
                onClick={() => setSelectedEmp(e.emp_id)}
              >
                <span className="emp-id">{e.emp_id}</span>
                <span className="emp-name">{e.name}</span>
                {e.flagCount > 0 && <span className="badge">{e.flagCount}</span>}
              </li>
            ))}
          </ul>
        </aside>

        <div className="employee-detail">
          {!selectedEmp ? (
            <p className="hint">Select an employee</p>
          ) : (
            <>
              <h3>{selectedEmpInfo?.name} ({selectedEmp})</h3>

              {emp?.bankSnapshot && Object.keys(emp.bankSnapshot).length > 0 && (
                <div className="bank-snapshot">
                  <h4>Leave banks</h4>
                  <BankTable snapshot={emp.bankSnapshot} />
                </div>
              )}

              <div className="totals-row">
                <div className="totals-box">
                  <h4>Week 1</h4>
                  <TotalsDisplay data={emp?.weeklyTotals?.week1} />
                </div>
                <div className="totals-box">
                  <h4>Week 2</h4>
                  <TotalsDisplay data={emp?.weeklyTotals?.week2} />
                </div>
                <div className="totals-box">
                  <h4>Period</h4>
                  <TotalsDisplay data={emp?.periodTotals} period />
                </div>
              </div>

              {emp?.weeklyHints?.length > 0 && (
                <div className="weekly-hints">
                  {emp.weeklyHints.map((h, i) => (
                    <p key={i} className="hint-box">{h.message}</p>
                  ))}
                </div>
              )}

              {emp?.flags?.length > 0 && (
                <div className="flags-row">
                  {emp.flags.map((f, i) => (
                    <span key={i} className={`flag-pill ${f.severity?.toLowerCase()}`} title={f.message}>
                      {f.code}
                    </span>
                  ))}
                </div>
              )}

              <div className="grid-section">
                <h4>Original Hours (TCP)</h4>
                <OriginalGrid grid={emp?.originalGrid} />
              </div>

              {emp?.flags?.some((f) => f.code === 'REG_OT_CAP') && (
                <div className="proposed-alert reg-ot-alert">
                  <strong>REG/OT conversion applied</strong> — We converted REG hrs ↔ OT/CT 1.0 to reach 40. Double-check the OT bucket (OT 1.0 vs CT EARN 1.0) matches what the employee would want.
                </div>
              )}
              {emp?.proposedGrid && (
                <>
                  <div className="proposed-totals-section">
                    <h4>Proposed totals</h4>
                    <p className="grid-hint">Totals after applying all suggestions</p>
                    <div className="totals-row">
                      <div className="totals-box">
                        <h4>Week 1</h4>
                        <TotalsDisplay data={emp.proposedTotals?.week1} />
                      </div>
                      <div className="totals-box">
                        <h4>Week 2</h4>
                        <TotalsDisplay data={emp.proposedTotals?.week2} />
                      </div>
                      <div className="totals-box">
                        <h4>Period</h4>
                        <TotalsDisplay data={emp.proposedTotals?.period} period />
                      </div>
                    </div>
                  </div>
                  <div className="grid-section proposed-grid-section">
                    <h4>Proposed grid</h4>
                    <p className="grid-hint">Result after applying all suggestions</p>
                    <OriginalGrid grid={emp.proposedGrid} />
                  </div>
                </>
              )}

              <div className="grid-section finalized-grid-section">
                <h4>Finalized grid</h4>
                <p className="grid-hint">
                  Editable — use for time exception slip. Copy from Proposed first, then tweak if needed.
                </p>
                <div className="finalized-actions">
                  <button
                    type="button"
                    className="btn-copy-proposed"
                    onClick={handleCopyFromProposed}
                    disabled={!emp?.proposedGrid}
                  >
                    Copy from Proposed
                  </button>
                </div>
                {effectiveFinalized ? (
                  <FinalizedGrid grid={effectiveFinalized} onCellChange={handleCellChange} />
                ) : (
                  <p className="hint">No hours data — copy from Proposed to start.</p>
                )}
              </div>

              {emp?.suggestions?.length > 0 && (
                <details className="suggestions-section">
                  <summary>Proposed changes ({emp.suggestions.length})</summary>
                  <ul>
                    {emp.suggestions.map((s, i) => (
                      <li key={i}>
                        <span className="suggestion-date">{formatSuggestionDate(s.date)}</span> — {s.original_hrs} {s.original_code} → {s.proposed_hrs} {s.proposed_code}: {s.reason}
                      </li>
                    ))}
                  </ul>
                </details>
              )}
            </>
          )}
        </div>
      </div>
    </section>
  )
}

function formatSuggestionDate(dateStr) {
  if (!dateStr) return ''
  const d = new Date(dateStr)
  return `${d.getMonth() + 1}/${d.getDate()}/${d.getFullYear()}`
}

function BankTable({ snapshot }) {
  const banks = Object.entries(snapshot)
  if (banks.length === 0) return null
  return (
    <table className="bank-table">
      <thead>
        <tr>
          <th>Bank</th>
          <th>Original</th>
          <th>Used (this period)</th>
          <th>Remaining</th>
        </tr>
      </thead>
      <tbody>
        {banks.map(([bank, v]) => (
          <tr key={bank}>
            <td>{bank}</td>
            <td>{v.original?.toFixed(2) ?? '—'}</td>
            <td>{v.used?.toFixed(2) ?? '—'}</td>
            <td className={v.remaining < 0 ? 'negative' : ''}>{v.remaining?.toFixed(2) ?? '—'}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function TotalsDisplay({ data, period }) {
  if (!data) return null
  return (
    <dl className="totals-dl">
      <dt>Regular Hrs</dt><dd>{data.paid ?? '—'}</dd>
      <dt>Premium</dt><dd>{data.premium ?? '—'}</dd>
      <dt>LWOP</dt><dd>{data.lwop ?? '—'}</dd>
      <dt>Documented</dt><dd>{data.documented ?? '—'}</dd>
      {!period && <><dt>OT Over 40</dt><dd>{data.otOver40 ?? '—'}</dd></>}
    </dl>
  )
}

function OriginalGrid({ grid }) {
  if (!grid?.dates?.length || !grid?.codes?.length) return <p>No hours.</p>
  const cells = grid.cells || {}
  const colTotals = {}
  grid.codes.forEach((c) => {
    colTotals[c] = grid.dates.reduce((sum, d) => sum + (parseFloat(cells[d.date]?.[c]) || 0), 0)
  })
  return (
    <div className="grid-wrap">
      <table className="hours-grid">
        <thead>
          <tr>
            <th>Date</th>
            {grid.codes.map((c) => (
              <th key={c}>{c}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {grid.dates.map((d) => (
            <tr key={d.date}>
              <td>{d.display} {d.dow}</td>
              {grid.codes.map((c) => (
                <td key={c}>{cells[d.date]?.[c] ?? ''}</td>
              ))}
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr className="grid-totals-row">
            <td>Total</td>
            {grid.codes.map((c) => (
              <td key={c}>{colTotals[c] ? colTotals[c].toFixed(2) : ''}</td>
            ))}
          </tr>
        </tfoot>
      </table>
    </div>
  )
}

function FinalizedGrid({ grid, onCellChange }) {
  if (!grid?.dates?.length || !grid?.codes?.length) return <p>No hours.</p>
  const cells = grid.cells || {}
  const colTotals = {}
  grid.codes.forEach((c) => {
    colTotals[c] = grid.dates.reduce((sum, d) => sum + (parseFloat(cells[d.date]?.[c]) || 0), 0)
  })
  return (
    <div className="grid-wrap">
      <table className="hours-grid finalized-grid">
        <thead>
          <tr>
            <th>Date</th>
            {grid.codes.map((c) => (
              <th key={c}>{c}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {grid.dates.map((d) => (
            <tr key={d.date}>
              <td>{d.display} {d.dow}</td>
              {grid.codes.map((c) => (
                <td key={c}>
                  <input
                    type="text"
                    size={4}
                    value={cells[d.date]?.[c] ?? ''}
                    onChange={(e) => onCellChange(d.date, c, e.target.value)}
                  />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr className="grid-totals-row">
            <td>Total</td>
            {grid.codes.map((c) => (
              <td key={c}>{colTotals[c] ? colTotals[c].toFixed(2) : ''}</td>
            ))}
          </tr>
        </tfoot>
      </table>
    </div>
  )
}
