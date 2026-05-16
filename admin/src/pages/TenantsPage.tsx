import { type FormEvent, useCallback, useEffect, useState } from 'react'
import { useDispatch, useSelector } from 'react-redux'
import { api, type ApiTenant } from '../api'
import { AdminLayout } from '../components/AdminLayout'
import { type RootState, setTenants } from '../store'

export function TenantsPage() {
  const dispatch = useDispatch()
  const { items } = useSelector((state: RootState) => state.tenants)
  const [id, setId] = useState('')
  const [name, setName] = useState('')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editName, setEditName] = useState('')

  const loadTenants = useCallback(async () => {
    dispatch(setTenants(await api<ApiTenant[]>('/api/admin/tenants')))
  }, [dispatch])

  useEffect(() => {
    const timer = window.setTimeout(() => loadTenants(), 0)
    return () => window.clearTimeout(timer)
  }, [loadTenants])

  async function createTenant(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setBusy(true)
    setMessage('正在创建租户...')
    try {
      await api('/api/admin/tenants', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id, name }),
      })
      setId('')
      setName('')
      setMessage('租户已创建')
      await loadTenants()
    } catch (err) {
      setMessage(err instanceof Error ? err.message : '创建租户失败')
    } finally {
      setBusy(false)
    }
  }

  async function updateTenantName(tenantId: string) {
    setBusy(true)
    setMessage('正在更新...')
    try {
      await api(`/api/admin/tenants/${tenantId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: editName }),
      })
      setEditingId(null)
      setEditName('')
      setMessage('租户已更新')
      await loadTenants()
    } catch (err) {
      setMessage(err instanceof Error ? err.message : '更新失败')
    } finally {
      setBusy(false)
    }
  }

  async function deleteTenant(tenantId: string) {
    if (!window.confirm(`确定删除租户 "${tenantId}"？`)) return
    setBusy(true)
    setMessage('正在删除...')
    try {
      await api(`/api/admin/tenants/${tenantId}`, { method: 'DELETE' })
      setMessage('租户已删除')
      await loadTenants()
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
          <p className="eyebrow">Tenants</p>
          <h2>租户管理</h2>
        </div>
        <button onClick={loadTenants} disabled={busy}>刷新</button>
      </header>

      <section className="panel">
        <h3>创建租户</h3>
        <form className="user-form" onSubmit={createTenant}>
          <input
            value={id}
            placeholder="租户 ID（小写字母、数字、下划线）"
            onChange={(event) => setId(event.target.value)}
            pattern="^[a-z0-9_-]+$"
            required
          />
          <input
            value={name}
            placeholder="租户名称"
            onChange={(event) => setName(event.target.value)}
            required
          />
          <button type="submit" disabled={busy}>创建</button>
        </form>
        {message && <div className="status">{message}</div>}
      </section>

      <section className="panel">
        <div className="table-header">
          <h3>租户列表</h3>
          <span>{items.length} 个租户</span>
        </div>
        <div className="table user-table">
          <div className="table-row user-row table-head">
            <span>ID</span>
            <span>名称</span>
            <span>创建时间</span>
            <span>操作</span>
          </div>
          {items.map((tenant) => (
            <div className="table-row user-row" key={tenant.id}>
              <span className="mono">{tenant.id}</span>
              <span>
                {editingId === tenant.id ? (
                  <span style={{ display: 'flex', gap: 8 }}>
                    <input
                      value={editName}
                      onChange={(event) => setEditName(event.target.value)}
                      style={{ width: 160 }}
                    />
                    <button className="compact" onClick={() => updateTenantName(tenant.id)} disabled={busy}>保存</button>
                    <button className="secondary compact" onClick={() => setEditingId(null)}>取消</button>
                  </span>
                ) : (
                  <span style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                    {tenant.name}
                    <button
                      className="compact"
                      style={{ padding: '2px 8px', fontSize: 12 }}
                      onClick={() => { setEditingId(tenant.id); setEditName(tenant.name) }}
                    >
                      编辑
                    </button>
                  </span>
                )}
              </span>
              <span>{tenant.created_at || '-'}</span>
              <span>
                {tenant.id !== 'default' && (
                  <button
                    className="danger compact"
                    onClick={() => deleteTenant(tenant.id)}
                    disabled={busy}
                  >
                    删除
                  </button>
                )}
              </span>
            </div>
          ))}
          {!items.length && <div className="empty"><p>暂无租户</p></div>}
        </div>
      </section>
    </AdminLayout>
  )
}
