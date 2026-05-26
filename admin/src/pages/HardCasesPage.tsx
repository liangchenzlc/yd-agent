import { useCallback, useEffect, useMemo, useState } from 'react'
import { useDispatch, useSelector } from 'react-redux'
import { api, type ApiTenant, type HardCaseRecord } from '../api'
import { AdminLayout } from '../components/AdminLayout'
import { type RootState, setHardCases } from '../store'

function parseWorkers(value: string): string[] {
  try {
    const parsed = JSON.parse(value)
    return Array.isArray(parsed) ? parsed.map(String) : []
  } catch {
    return []
  }
}

function reasonOf(item: HardCaseRecord) {
  if ((item.rating ?? 0) < 0) return '用户点踩'
  if ((item.confidence ?? 1) < 0.35) return '低置信度'
  if (item.answer.includes('未找到')) return '未找到答案'
  return '待复查'
}

export function HardCasesPage() {
  const dispatch = useDispatch()
  const { items } = useSelector((state: RootState) => state.hardCases)
  const { user } = useSelector((state: RootState) => state.auth)
  const isSuperAdmin = user?.role === 'super_admin'
  const [keyword, setKeyword] = useState('')
  const [expandedId, setExpandedId] = useState<number | null>(null)
  const [message, setMessage] = useState('')
  const [tenants, setTenants] = useState<ApiTenant[]>([])
  const [selectedTenant, setSelectedTenant] = useState('')

  useEffect(() => {
    if (isSuperAdmin) {
      api<ApiTenant[]>('/api/admin/tenants').then(setTenants).catch(() => {})
    }
  }, [isSuperAdmin])

  const loadHardCases = useCallback(async () => {
    try {
      const params = isSuperAdmin && selectedTenant ? `?tenant_id=${selectedTenant}` : ''
      dispatch(setHardCases(await api<HardCaseRecord[]>(`/api/admin/hard-cases${params}`)))
      setMessage('')
    } catch (err) {
      setMessage(err instanceof Error ? err.message : '加载难例失败')
    }
  }, [dispatch, isSuperAdmin, selectedTenant])

  useEffect(() => {
    const timer = window.setTimeout(() => {
      loadHardCases()
    }, 0)
    return () => window.clearTimeout(timer)
  }, [loadHardCases])

  const filteredItems = useMemo(() => {
    const query = keyword.trim().toLowerCase()
    return items.filter((item) => {
      if (!query) return true
      return (
        item.question.toLowerCase().includes(query) ||
        item.answer.toLowerCase().includes(query) ||
        (item.comment || '').toLowerCase().includes(query)
      )
    })
  }, [items, keyword])

  return (
    <AdminLayout>
      <header className="page-header">
        <div>
          <p className="eyebrow">Hard Cases</p>
          <h2>难例池</h2>
        </div>
        <button onClick={loadHardCases}>刷新</button>
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

      <section className="panel filter-panel single">
        <input
          value={keyword}
          placeholder="搜索问题、答案或反馈备注"
          onChange={(event) => setKeyword(event.target.value)}
        />
      </section>

      {message && <div className="status">{message}</div>}

      <section className="panel">
        <div className="table-header">
          <h3>待复查问题</h3>
          <span>{filteredItems.length} / {items.length} 条</span>
        </div>
        <div className="qa-log-list">
          {filteredItems.map((item) => {
            const workers = parseWorkers(item.workers)
            return (
              <article className="qa-log-card" key={item.id}>
                <div className="qa-log-top">
                  <div>
                    <span className="badge">{reasonOf(item)}</span>
                    <span className="muted"> #{item.id} · user {item.user_id}</span>
                    {item.tenant_name && <span className="pill">{item.tenant_name}</span>}
                  </div>
                  <div className="qa-log-meta">
                    <span>{workers.join(', ') || 'none'}</span>
                    <span>{item.created_at}</span>
                  </div>
                </div>
                <h4>{item.question}</h4>
                <p>{item.answer}</p>
                {item.comment && <div className="status">用户反馈：{item.comment}</div>}
                <button
                  className="secondary compact"
                  onClick={() => setExpandedId(expandedId === item.id ? null : item.id)}
                >
                  {expandedId === item.id ? '收起详情' : '查看详情'}
                </button>
                {expandedId === item.id && (
                  <div className="qa-log-detail">
                    <strong>调度理由</strong>
                    <pre>{item.dispatch_reasoning || '-'}</pre>
                    <strong>Worker 原始结果</strong>
                    <pre>{item.worker_results || '-'}</pre>
                  </div>
                )}
              </article>
            )
          })}
          {!filteredItems.length && <div className="empty">暂无难例</div>}
        </div>
      </section>
    </AdminLayout>
  )
}
