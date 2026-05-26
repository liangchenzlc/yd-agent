import { useCallback, useEffect, useMemo, useState } from 'react'
import { useDispatch, useSelector } from 'react-redux'
import { api, type ApiTenant, type KnowledgeGapRecord } from '../api'
import { AdminLayout } from '../components/AdminLayout'
import { type RootState, setKnowledgeGaps } from '../store'

function topReason(item: KnowledgeGapRecord) {
  const entries: Array<[string, number]> = [
    ['未找到答案', item.reasons.not_found],
    ['低置信度', item.reasons.low_confidence],
    ['用户点踩', item.reasons.negative_feedback],
  ]
  return entries.sort((a, b) => b[1] - a[1])[0][0]
}

export function KnowledgeGapsPage() {
  const dispatch = useDispatch()
  const { items } = useSelector((state: RootState) => state.knowledgeGaps)
  const { user } = useSelector((state: RootState) => state.auth)
  const isSuperAdmin = user?.role === 'super_admin'
  const [keyword, setKeyword] = useState('')
  const [expandedQuestion, setExpandedQuestion] = useState<string | null>(null)
  const [message, setMessage] = useState('')
  const [tenants, setTenants] = useState<ApiTenant[]>([])
  const [selectedTenant, setSelectedTenant] = useState('')

  useEffect(() => {
    if (isSuperAdmin) {
      api<ApiTenant[]>('/api/admin/tenants').then(setTenants).catch(() => {})
    }
  }, [isSuperAdmin])

  const loadKnowledgeGaps = useCallback(async () => {
    try {
      const params = isSuperAdmin && selectedTenant ? `?tenant_id=${selectedTenant}` : ''
      dispatch(setKnowledgeGaps(await api<KnowledgeGapRecord[]>(`/api/admin/knowledge-gaps${params}`)))
      setMessage('')
    } catch (err) {
      setMessage(err instanceof Error ? err.message : '加载知识缺口失败')
    }
  }, [dispatch, isSuperAdmin, selectedTenant])

  useEffect(() => {
    const timer = window.setTimeout(() => {
      loadKnowledgeGaps()
    }, 0)
    return () => window.clearTimeout(timer)
  }, [loadKnowledgeGaps])

  const filteredItems = useMemo(() => {
    const query = keyword.trim().toLowerCase()
    return items.filter((item) => !query || item.question.toLowerCase().includes(query))
  }, [items, keyword])

  return (
    <AdminLayout>
      <header className="page-header">
        <div>
          <p className="eyebrow">Knowledge Gaps</p>
          <h2>知识缺口报表</h2>
        </div>
        <button onClick={loadKnowledgeGaps}>刷新</button>
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
          placeholder="搜索高频问题"
          onChange={(event) => setKeyword(event.target.value)}
        />
      </section>

      {message && <div className="status">{message}</div>}

      <section className="gap-grid">
        {filteredItems.map((item) => (
          <article className="gap-card" key={item.question}>
            <div className="gap-top">
              <span className="badge">{topReason(item)}</span>
              <span className="muted">{item.count} 次 · {item.latest_at}</span>
            </div>
            <h3>{item.question}</h3>
            <div className="reason-bars">
              <span>未找到 {item.reasons.not_found}</span>
              <span>低置信度 {item.reasons.low_confidence}</span>
              <span>点踩 {item.reasons.negative_feedback}</span>
            </div>
            <p>{item.suggestion}</p>
            <button
              className="secondary compact"
              onClick={() => setExpandedQuestion(expandedQuestion === item.question ? null : item.question)}
            >
              {expandedQuestion === item.question ? '收起样例' : '查看样例'}
            </button>
            {expandedQuestion === item.question && (
              <div className="qa-log-detail">
                {item.examples.map((example) => (
                  <pre key={example.id}>
                    {`#${example.id} ${example.question}\n${example.answer}${example.comment ? `\n反馈：${example.comment}` : ''}`}
                  </pre>
                ))}
              </div>
            )}
          </article>
        ))}
        {!filteredItems.length && (
          <div className="empty">
            <p>暂无知识缺口</p>
            <p style={{ fontSize: 13, marginTop: 4 }}>系统运行后会自动统计高频但未找到答案的问题</p>
          </div>
        )}
      </section>
    </AdminLayout>
  )
}
