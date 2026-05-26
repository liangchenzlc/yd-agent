import { useCallback, useEffect, useMemo, useState } from 'react'
import { useDispatch, useSelector } from 'react-redux'
import { api, type ApiTenant, type QaLogRecord } from '../api'
import { AdminLayout } from '../components/AdminLayout'
import { type RootState, setQaLogs } from '../store'

type ParsedQaLog = QaLogRecord & {
  workerList: string[]
}

function parseWorkers(value: string): string[] {
  try {
    const parsed = JSON.parse(value)
    return Array.isArray(parsed) ? parsed.map(String) : []
  } catch {
    return []
  }
}

function formatConfidence(value: number | null) {
  if (value === null || value === undefined) return '-'
  return `${Math.round(value * 100)}%`
}

export function QaLogsPage() {
  const dispatch = useDispatch()
  const { items } = useSelector((state: RootState) => state.qaLogs)
  const { user } = useSelector((state: RootState) => state.auth)
  const isSuperAdmin = user?.role === 'super_admin'
  const [keyword, setKeyword] = useState('')
  const [worker, setWorker] = useState('all')
  const [lowConfidenceOnly, setLowConfidenceOnly] = useState(false)
  const [expandedId, setExpandedId] = useState<number | null>(null)
  const [message, setMessage] = useState('')
  const [tenants, setTenants] = useState<ApiTenant[]>([])
  const [selectedTenant, setSelectedTenant] = useState('')

  useEffect(() => {
    if (isSuperAdmin) {
      api<ApiTenant[]>('/api/admin/tenants').then(setTenants).catch(() => {})
    }
  }, [isSuperAdmin])

  const loadQaLogs = useCallback(async () => {
    try {
      const params = isSuperAdmin && selectedTenant ? `?tenant_id=${selectedTenant}` : ''
      dispatch(setQaLogs(await api<QaLogRecord[]>(`/api/admin/qa-logs${params}`)))
      setMessage('')
    } catch (err) {
      setMessage(err instanceof Error ? err.message : '加载问答日志失败')
    }
  }, [dispatch, isSuperAdmin, selectedTenant])

  useEffect(() => {
    const timer = window.setTimeout(() => {
      loadQaLogs()
    }, 0)
    return () => window.clearTimeout(timer)
  }, [loadQaLogs])

  const parsedItems = useMemo<ParsedQaLog[]>(
    () => items.map((item) => ({ ...item, workerList: parseWorkers(item.workers) })),
    [items],
  )

  const workerOptions = useMemo(() => {
    const values = new Set<string>()
    parsedItems.forEach((item) => item.workerList.forEach((name) => values.add(name)))
    return Array.from(values).sort()
  }, [parsedItems])

  const filteredItems = useMemo(() => {
    const query = keyword.trim().toLowerCase()
    return parsedItems.filter((item) => {
      const matchesKeyword =
        !query ||
        item.question.toLowerCase().includes(query) ||
        item.answer.toLowerCase().includes(query) ||
        item.dispatch_reasoning.toLowerCase().includes(query)
      const matchesWorker = worker === 'all' || item.workerList.includes(worker)
      const matchesConfidence = !lowConfidenceOnly || (item.confidence ?? 1) < 0.35
      return matchesKeyword && matchesWorker && matchesConfidence
    })
  }, [keyword, lowConfidenceOnly, parsedItems, worker])

  return (
    <AdminLayout>
      <header className="page-header">
        <div>
          <p className="eyebrow">QA Logs</p>
          <h2>问答日志</h2>
        </div>
        <button onClick={loadQaLogs}>刷新</button>
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

      <section className="panel filter-panel">
        <input
          value={keyword}
          placeholder="搜索问题、答案或调度理由"
          onChange={(event) => setKeyword(event.target.value)}
        />
        <select value={worker} onChange={(event) => setWorker(event.target.value)}>
          <option value="all">全部 Worker</option>
          {workerOptions.map((name) => (
            <option key={name} value={name}>
              {name}
            </option>
          ))}
        </select>
        <label className="checkbox-label">
          <input
            type="checkbox"
            checked={lowConfidenceOnly}
            onChange={(event) => setLowConfidenceOnly(event.target.checked)}
          />
          仅低置信度
        </label>
      </section>

      {message && <div className="status">{message}</div>}

      <section className="panel">
        <div className="table-header">
          <h3>日志列表</h3>
          <span>{filteredItems.length} / {items.length} 条</span>
        </div>
        <div className="qa-log-list">
          {filteredItems.map((item) => (
            <article className="qa-log-card" key={item.id}>
              <div className="qa-log-top">
                <div>
                  <span className="mono">#{item.id}</span>
                  <span className="muted"> session {item.session_id}</span>
                  {item.tenant_name && <span className="pill">{item.tenant_name}</span>}
                </div>
                <div className="qa-log-meta">
                  <span>{item.workerList.join(', ') || 'none'}</span>
                  <span>{formatConfidence(item.confidence)}</span>
                  <span>{item.created_at}</span>
                </div>
              </div>
              <h4>{item.question}</h4>
              <p>{item.answer}</p>
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
          ))}
          {!filteredItems.length && <div className="empty">暂无匹配日志</div>}
        </div>
      </section>
    </AdminLayout>
  )
}
