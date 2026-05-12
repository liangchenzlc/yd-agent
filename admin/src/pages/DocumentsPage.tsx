import { type ChangeEvent, useCallback, useEffect, useState } from 'react'
import { useDispatch, useSelector } from 'react-redux'
import { api, type DocumentRecord } from '../api'
import { AdminLayout } from '../components/AdminLayout'
import { type RootState, setDocuments } from '../store'

export function DocumentsPage() {
  const dispatch = useDispatch()
  const { items } = useSelector((state: RootState) => state.documents)
  const [file, setFile] = useState<File | null>(null)
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)

  const loadDocuments = useCallback(async () => {
    dispatch(setDocuments(await api<DocumentRecord[]>('/api/admin/documents')))
  }, [dispatch])

  useEffect(() => {
    loadDocuments()
  }, [loadDocuments])

  function onFileChange(event: ChangeEvent<HTMLInputElement>) {
    setFile(event.target.files?.[0] || null)
  }

  async function uploadDocument() {
    if (!file) {
      setMessage('请选择要上传的文档')
      return
    }
    setBusy(true)
    setMessage('正在上传并索引...')
    try {
      const form = new FormData()
      form.append('file', file)
      await api('/api/admin/documents', {
        method: 'POST',
        body: form,
      })
      setFile(null)
      setMessage('文档已上传并完成索引')
      await loadDocuments()
    } catch (err) {
      setMessage(err instanceof Error ? err.message : '上传失败')
    } finally {
      setBusy(false)
    }
  }

  async function deleteDocument(docId: string) {
    if (!window.confirm(`确认删除文档 ${docId}？`)) return
    setBusy(true)
    setMessage('正在删除文档...')
    try {
      await api(`/api/admin/documents/${docId}`, { method: 'DELETE' })
      setMessage('文档已删除')
      await loadDocuments()
    } catch (err) {
      setMessage(err instanceof Error ? err.message : '删除失败')
    } finally {
      setBusy(false)
    }
  }

  return (
    <AdminLayout>
        <header className="page-header">
          <div>
            <p className="eyebrow">Documents</p>
            <h2>文档管理</h2>
          </div>
          <button onClick={loadDocuments} disabled={busy}>刷新</button>
        </header>

        <section className="panel upload-panel">
          <div>
            <h3>上传知识文档</h3>
            <p>上传后会调用 GraphRAG 摄入流程，生成 chunk、实体和关系索引。</p>
          </div>
          <div className="upload-actions">
            <input type="file" onChange={onFileChange} />
            <button onClick={uploadDocument} disabled={busy}>上传并索引</button>
          </div>
          {message && <div className="status">{message}</div>}
        </section>

        <section className="panel">
          <div className="table-header">
            <h3>已摄入文档</h3>
            <span>{items.length} 个文档</span>
          </div>
          <div className="table">
            <div className="table-row table-head">
              <span>文档 ID</span>
              <span>来源</span>
              <span>Chunks</span>
              <span>Entities</span>
              <span>Status</span>
              <span>操作</span>
            </div>
            {items.map((doc) => (
              <div className="table-row" key={doc.id}>
                <span className="mono">{doc.id}</span>
                <span title={doc.source}>{doc.source || '-'}</span>
                <span>{doc.chunks}</span>
                <span>{doc.entities}</span>
                <span>{doc.status || 'ready'}</span>
                <span>
                  <button className="danger" onClick={() => deleteDocument(doc.id)} disabled={busy}>
                    删除
                  </button>
                </span>
              </div>
            ))}
            {!items.length && <div className="empty">暂无文档</div>}
          </div>
        </section>
    </AdminLayout>
  )
}
