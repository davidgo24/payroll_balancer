import { useState, useEffect } from 'react'

export default function UploadScreen({ onRun, onLoadPeriod, loading, error }) {
  const [mode, setMode] = useState('create')
  const [periodIds, setPeriodIds] = useState([])
  const [periodEndDate, setPeriodEndDate] = useState('')
  const [periodId, setPeriodId] = useState('')
  const [reuseAccrual, setReuseAccrual] = useState(true)
  const [tcpFile, setTcpFile] = useState(null)
  const [accrualFile, setAccrualFile] = useState(null)

  const fetchPeriods = () => {
    fetch('/api/periods')
      .then((r) => {
        if (!r.ok) throw new Error(`Backend returned ${r.status}`)
        return r.json()
      })
      .then((d) => setPeriodIds(d.periodIds || []))
      .catch(() => setPeriodIds([]))
  }

  useEffect(() => fetchPeriods(), [])

  const handleClearAll = () => {
    if (!window.confirm('Delete all stored periods? This cannot be undone.')) return
    fetch('/api/periods?all=true', { method: 'DELETE' })
      .then((r) => r.json())
      .then(() => {
        setPeriodIds([])
        setPeriodId('')
      })
      .catch((err) => alert('Failed to delete: ' + (err?.message || err)))
  }

  const handleSubmit = (e) => {
    e.preventDefault()
    const fd = new FormData()
    fd.append('tcp_file', tcpFile)
    fd.append('append', String(mode === 'append'))
    if (mode === 'create') {
      fd.append('period_end_date', periodEndDate)
      fd.append('accrual_file', accrualFile)
      if (!periodEndDate || !accrualFile) {
        return
      }
    } else {
      fd.append('period_id', periodId)
      fd.append('reuse_accrual', String(reuseAccrual))
      if (!periodId) return
      if (!reuseAccrual) {
        fd.append('accrual_file', accrualFile)
      }
    }
    onRun(fd)
  }

  const satWarning = periodEndDate && !isSaturday(periodEndDate)

  return (
    <section className="upload-screen">
      {periodIds.length > 0 && (
        <div className="view-existing">
          <div className="view-existing-header">
            <label>View existing period</label>
            <button type="button" className="btn-clear-all" onClick={handleClearAll} title="Delete all stored periods">
              Clear all
            </button>
          </div>
          <div className="view-existing-row">
            <select
              value={periodId || ''}
              onChange={(e) => setPeriodId(e.target.value)}
            >
              <option value="">Select period...</option>
              {periodIds.map((id) => (
                <option key={id} value={id}>{id}</option>
              ))}
            </select>
            <button
              type="button"
              onClick={() => onLoadPeriod?.(periodId)}
              disabled={loading || !periodId}
            >
              {loading ? 'Loading...' : 'View'}
            </button>
          </div>
        </div>
      )}
      <form onSubmit={handleSubmit} className="upload-form">
        <div className="mode-tabs">
          <button type="button" className={mode === 'create' ? 'active' : ''} onClick={() => setMode('create')}>
            New Period
          </button>
          <button type="button" className={mode === 'append' ? 'active' : ''} onClick={() => setMode('append')}>
            Append Week 2
          </button>
        </div>

        {mode === 'create' && (
          <>
            <div className="form-group">
              <label>Period End Date (Saturday)</label>
              <input
                type="date"
                value={periodEndDate}
                onChange={(e) => setPeriodEndDate(e.target.value)}
                required
              />
              {satWarning && (
                <p className="warning">Period end should be a Saturday. You can continue anyway.</p>
              )}
            </div>
            <div className="form-group">
              <label>Accrual Excel</label>
              <input
                type="file"
                accept=".xlsx,.xls"
                onChange={(e) => setAccrualFile(e.target.files?.[0])}
                required
              />
            </div>
          </>
        )}

        {mode === 'append' && (
          <>
            <div className="form-group">
              <label>Period</label>
              <select value={periodId} onChange={(e) => setPeriodId(e.target.value)} required>
                <option value="">Select period...</option>
                {periodIds.map((id) => (
                  <option key={id} value={id}>{id}</option>
                ))}
              </select>
            </div>
            <div className="form-group checkbox">
              <label>
                <input type="checkbox" checked={reuseAccrual} onChange={(e) => setReuseAccrual(e.target.checked)} />
                Reuse stored accrual snapshot
              </label>
            </div>
            {!reuseAccrual && (
              <div className="form-group">
                <label>New Accrual Excel</label>
                <input
                  type="file"
                  accept=".xlsx,.xls"
                  onChange={(e) => setAccrualFile(e.target.files?.[0])}
                />
              </div>
            )}
          </>
        )}

        <div className="form-group">
          <label>TCP CSV</label>
          <input
            type="file"
            accept=".csv"
            onChange={(e) => setTcpFile(e.target.files?.[0])}
            required
          />
        </div>

        {error && <p className="error">{error}</p>}
        <button type="submit" disabled={loading || !tcpFile}>
          {loading ? 'Running...' : mode === 'create' ? 'Run' : 'Append'}
        </button>
      </form>
    </section>
  )
}

function isSaturday(dateStr) {
  if (!dateStr) return false
  const d = new Date(dateStr)
  return d.getDay() === 6
}
