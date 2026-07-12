import { useEffect, useState } from 'react'

const API_BASE = 'http://127.0.0.1:8123'

export default function App() {
  const [stats, setStats] = useState(null)
  const [snapshot, setSnapshot] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    Promise.all([
      fetch(`${API_BASE}/api/overview/headline-stats`).then(r => r.json()),
      fetch(`${API_BASE}/api/overview/rating-snapshot`).then(r => r.json()),
    ])
      .then(([statsBody, snapshotBody]) => {
        setStats(statsBody)
        setSnapshot(snapshotBody)
      })
      .catch(e => setError(String(e)))
  }, [])

  if (error) return <div>Error fetching from API: {error}</div>
  if (!stats || !snapshot) return <div>Loading...</div>

  return (
    <div style={{ fontFamily: 'sans-serif', padding: '2rem' }}>
      <h1>Your chess identity</h1>
      <p style={{ fontSize: '2rem' }}>{snapshot.current_rating ?? '--'}</p>
      <div style={{ display: 'flex', gap: '2rem' }}>
        <div>
          <div style={{ fontSize: '1.5rem' }}>{stats.total_games.toLocaleString()}</div>
          <div>Total games</div>
        </div>
        <div>
          <div style={{ fontSize: '1.5rem' }}>{stats.analyzed_games.toLocaleString()}</div>
          <div>Analyzed games</div>
        </div>
        <div>
          <div style={{ fontSize: '1.5rem' }}>
            {stats.win_pct != null ? `${stats.win_pct.toFixed(1)}%` : '--'}
          </div>
          <div>Win rate</div>
        </div>
        <div>
          <div style={{ fontSize: '1.5rem' }}>
            {stats.acpl != null ? stats.acpl.toFixed(1) : '--'}
          </div>
          <div>ACPL</div>
        </div>
      </div>
    </div>
  )
}
