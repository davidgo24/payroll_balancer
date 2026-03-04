import { useState, useCallback } from 'react'
import './App.css'
import UploadScreen from './UploadScreen'
import ResultsScreen from './ResultsScreen'

const API_BASE = '/api'

export default function App() {
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)

  const handleLoadPeriod = useCallback(async (periodId) => {
    if (!periodId) return
    setError(null)
    setLoading(true)
    try {
      const r = await fetch(`${API_BASE}/run?period_id=${encodeURIComponent(periodId)}`)
      if (!r.ok) {
        const t = await r.text()
        throw new Error(t || `HTTP ${r.status}`)
      }
      const data = await r.json()
      setResult(data)
    } catch (e) {
      const msg = e.message.includes('fetch') || e.message.includes('Network')
        ? 'Cannot reach backend. Run: uvicorn api.main:app --reload --port 8001'
        : e.message
      setError(msg)
    } finally {
      setLoading(false)
    }
  }, [])

  const handleRun = useCallback(async (formData) => {
    setError(null)
    setLoading(true)
    try {
      const r = await fetch(`${API_BASE}/run`, {
        method: 'POST',
        body: formData,
      })
      if (!r.ok) {
        const t = await r.text()
        if (r.status === 404) {
          throw new Error('Backend returned 404. Start it with: uvicorn api.main:app --reload --port 8001')
        }
        if (r.status === 400 && t.includes('already exists')) {
          const match = t.match(/Period ([0-9-]+) already exists/) || t.match(/"([^"]+)" already exists/)
          const pid = match ? match[1] : null
          throw new Error(pid ? `PERIOD_EXISTS:${pid}` : t)
        }
        throw new Error(t || `HTTP ${r.status}`)
      }
      const data = await r.json()
      setResult(data)
    } catch (e) {
      if (e.message.startsWith('PERIOD_EXISTS:')) {
        handleLoadPeriod(e.message.replace('PERIOD_EXISTS:', ''))
        return
      }
      const msg = e.message.includes('fetch') || e.message.includes('Network')
        ? 'Cannot reach backend. Run: uvicorn api.main:app --reload --port 8001'
        : e.message
      setError(msg)
    } finally {
      setLoading(false)
    }
  }, [handleLoadPeriod])

  const handleReset = useCallback(() => {
    setResult(null)
    setError(null)
  }, [])

  return (
    <div className="app">
      <header className="app-header">
        <h1>Payroll Balancer</h1>
      </header>
      <main className="app-main">
        {!result ? (
          <UploadScreen
            onRun={handleRun}
            onLoadPeriod={handleLoadPeriod}
            loading={loading}
            error={error}
          />
        ) : (
          <ResultsScreen result={result} onReset={handleReset} />
        )}
      </main>
    </div>
  )
}
