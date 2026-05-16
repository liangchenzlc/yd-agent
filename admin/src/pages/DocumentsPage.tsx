import { type ChangeEvent, useCallback, useEffect, useState } from 'react'
import { useDispatch, useSelector } from 'react-redux'
import { api, type DocumentRecord } from '../api'
import { AdminLayout } from '../components/AdminLayout'
import { type RootState, setDocuments } from '../store'

function UploadIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" /><polyline points="17 8 12 3 7 8" /><line x1="12" y1="3" x2="12" y2="15" />
    </svg>
  )
}

function TrashIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" style={{ verticalAlign: 'middle', marginRight: 4 }}>
      <polyline points="3 6 5 6 21 6" /><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
    </svg>
  )
}

export function DocumentsPage() {
  const dispatch = useDispatch()
  const { items } = useSelector((state: RootState) => state.documents)
  const [file, setFile] = useState<File | null>(null)
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const [dragOver, setDragOver] = useState(false)

  const loadDocuments = useCallback(async () => {
    try {
      dispatch(setDocuments(await api<DocumentRecord[]>('/api/admin/documents')))
    } catch {
      setMessage('加载文档列表失败')
    }
  }, [dispatch])

  useEffect(() => { loadDocuments() }, [loadDocuments])

  function onFileChange(event: ChangeEvent<HTMLInputElement>) {
    setFile(event.target.files?.[0] || null)
  }

  function onDragOver(event: React.DragEvent) {
    event.preventDefault()
    setDragOver(true)
  }

  function onDragLeave() { setDragOver(false) }

  function onDrop(event: React.DragEvent) {
    event.preventDefault()
    setDragOver(false)
    const dropped = event.dataTransfer.files?.[0]
    if (dropped) setFile(dropped)
  }

  async function uploadDocument() {
    if (!file) { setMessage('请选择要上传的文档'); return }
    setBusy(true)
    setMessage('正在上传并索引...')
    try {
      const form = new FormData()
      form.append('file', file)
      await api('/api/admin/documents', { method: 'POST', body: form })
      setFile(null)
      setMessage('文档已上传并完成索引')
      await loadDocuments()
    } catch (err) {
      setMessage(err instanceof Error ? err.message : '上传失败')
    } finally { setBusy(false) }
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
    } finally { setBusy(false) }
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
          <p>支持 PDF、TXT、Markdown、JSON、CSV、Word 格式，单个文件不超过 50 MB</p>
        </div>
        <div
          className={`upload-zone ${dragOver ? 'drag-over' : ''}`}
          onDragOver={onDragOver}
          onDragLeave={onDragLeave}
          onDrop={onDrop}
        >
          <UploadIcon />
          <span>{file ? file.name : '拖拽文件到此处或点击选择'}</span>
          <input
            type="file"
            onChange={onFileChange}
            className="file-input"
            accept=".pdf,.txt,.md,.json,.csv,.doc,.docx"
          />
        </div>
        <div className="upload-actions">
          <button onClick={uploadDocument} disabled={busy || !file}>
            {busy ? '索引中...' : '上传并索引'}
          </button>
          {file && <button className="secondary compact" onClick={() => setFile(null)} style={{ width: 'auto' }}>取消选择</button>}
        </div>
        {message && <div className="status">{message}</div>}
      </section>

      <section className="panel">
        <div className="table-header">
          <h3>已摄入文档</h3>
          <span>{items.length} 个文档</span>
        </div>
        {items.length > 0 ? (
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
                  <button className="danger compact" onClick={() => deleteDocument(doc.id)} disabled={busy} aria-label={`删除文档 ${doc.id}`}>
                    <TrashIcon />删除
                  </button>
                </span>
              </div>
            ))}
          </div>
        ) : (
          <div className="empty">
            <p>暂无文档</p>
            <p style={{ fontSize: 13, marginTop: 4 }}>上传知识文档后，系统将自动提取实体和关系索引</p>
          </div>
        )}
      </section>
    </AdminLayout>
  )
}
