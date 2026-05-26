import { useCallback, useEffect, useState } from 'react'
import { useSelector } from 'react-redux'
import { api, type ApiTenant } from '../api'
import { AdminLayout } from '../components/AdminLayout'
import { type RootState } from '../store'

type DailyStats = {
  date: string
  api_calls: number
  tokens: { total: number; input: number; output: number }
}

function SkeletonCard() {
  return (
    <div className="stat-card" style={{ opacity: 0.5 }}>
      <h3>&nbsp;</h3>
      <div className="stat-value" style={{ background: '#e2e8f0', borderRadius: 4, height: 40, width: '60%', margin: '8px auto' }} />
      <div className="stat-label">&nbsp;</div>
    </div>
  )
}

export function UsagePage() {
  const { user } = useSelector((state: RootState) => state.auth)
  const isSuperAdmin = user?.role === 'super_admin'
  const [stats, setStats] = useState<DailyStats | null>(null)
  const [busy, setBusy] = useState(false)
  const [tenants, setTenants] = useState<ApiTenant[]>([])
  const [selectedTenant, setSelectedTenant] = useState('')

  useEffect(() => {
    if (isSuperAdmin) {
      api<ApiTenant[]>('/api/admin/tenants').then(setTenants).catch(() => {})
    }
  }, [isSuperAdmin])

  const loadStats = useCallback(async () => {
    setBusy(true)
    try {
      const params = isSuperAdmin && selectedTenant ? `?tenant_id=${selectedTenant}` : ''
      setStats(await api<DailyStats>(`/api/admin/usage${params}`))
    } catch { /* silently fail */ }
    finally { setBusy(false) }
  }, [isSuperAdmin, selectedTenant])

  useEffect(() => { loadStats() }, [loadStats])

  useEffect(() => { loadStats() }, [loadStats])

  return (
    <AdminLayout>
      <header className="page-header">
        <div>
          <p className="eyebrow">Usage</p>
          <h2>用量统计</h2>
        </div>
        <button onClick={loadStats} disabled={busy}>刷新</button>
      </header>

      {isSuperAdmin && (
        <section className="panel filter-panel" style={{ gridTemplateColumns: 'minmax(200px, 1fr)' }}>
          <select value={selectedTenant} onChange={(e) => setSelectedTenant(e.target.value)}>
            <option value="">全部租户</option>
            {tenants.map((t) => (
              <option key={t.id} value={t.id}>{t.name} ({t.id})</option>
            ))}
          </select>
        </section>
      )}

      <section className="stats-cards">
        {stats ? (
          <>
            <div className="stat-card">
              <h3>API 调用</h3>
              <div className="stat-value">{stats.api_calls.toLocaleString()}</div>
              <div className="stat-label">{stats.date}</div>
            </div>
            <div className="stat-card">
              <h3>Token 消耗</h3>
              <div className="stat-value">{stats.tokens.total.toLocaleString()}</div>
              <div className="stat-label">总计</div>
            </div>
            <div className="stat-card">
              <h3>输入 Token</h3>
              <div className="stat-value">{stats.tokens.input.toLocaleString()}</div>
              <div className="stat-label">估算值</div>
            </div>
            <div className="stat-card">
              <h3>输出 Token</h3>
              <div className="stat-value">{stats.tokens.output.toLocaleString()}</div>
              <div className="stat-label">估算值</div>
            </div>
          </>
        ) : (
          <>
            <SkeletonCard />
            <SkeletonCard />
            <SkeletonCard />
            <SkeletonCard />
          </>
        )}
      </section>
    </AdminLayout>
  )
}
