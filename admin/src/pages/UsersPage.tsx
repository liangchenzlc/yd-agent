import { type FormEvent, useCallback, useEffect, useState } from 'react'
import { useDispatch, useSelector } from 'react-redux'
import { api, type ApiTenant, type ApiUser } from '../api'
import { AdminLayout } from '../components/AdminLayout'
import { type RootState, setTenants, setUsers } from '../store'

export function UsersPage() {
  const dispatch = useDispatch()
  const { items } = useSelector((state: RootState) => state.users)
  const { user: currentUser } = useSelector((state: RootState) => state.auth)
  const { items: tenants } = useSelector((state: RootState) => state.tenants)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [tenantId, setTenantId] = useState('default')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)

  const loadUsers = useCallback(async () => {
    dispatch(setUsers(await api<ApiUser[]>('/api/admin/users')))
  }, [dispatch])

  const loadTenants = useCallback(async () => {
    try {
      dispatch(setTenants(await api<ApiTenant[]>('/api/admin/tenants')))
    } catch {
      // 忽略
    }
  }, [dispatch])

  useEffect(() => {
    const timer = window.setTimeout(() => {
      loadUsers()
      loadTenants()
      if (currentUser?.tenant_id) {
        setTenantId(currentUser.tenant_id)
      }
    }, 0)
    return () => window.clearTimeout(timer)
  }, [loadUsers, loadTenants, currentUser])

  async function createUser(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setBusy(true)
    setMessage('正在创建用户...')
    try {
      const body: Record<string, string> = { username, password, tenant_id: tenantId }
      await api('/api/admin/users', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      setUsername('')
      setPassword('')
      setMessage('用户已创建')
      await loadUsers()
    } catch (err) {
      setMessage(err instanceof Error ? err.message : '创建用户失败')
    } finally {
      setBusy(false)
    }
  }

  async function toggleUser(userId: number, enabled: boolean) {
    setBusy(true)
    setMessage('正在更新用户...')
    try {
      await api(`/api/admin/users/${userId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled }),
      })
      setMessage('用户已更新')
      await loadUsers()
    } catch (err) {
      setMessage(err instanceof Error ? err.message : '更新用户失败')
    } finally {
      setBusy(false)
    }
  }

  return (
    <AdminLayout>
      <header className="page-header">
        <div>
          <p className="eyebrow">Users</p>
          <h2>用户管理</h2>
        </div>
        <button onClick={loadUsers} disabled={busy}>刷新</button>
      </header>

      <section className="panel">
        <h3>创建用户</h3>
        <form className="user-form" onSubmit={createUser}>
          <input
            value={username}
            placeholder="用户名"
            onChange={(event) => setUsername(event.target.value)}
            required
          />
          <input
            value={password}
            type="password"
            placeholder="初始密码"
            onChange={(event) => setPassword(event.target.value)}
            required
          />
          <select value={tenantId} onChange={(event) => setTenantId(event.target.value)}>
            {tenants.length > 0
              ? tenants.map((t) => (
                  <option value={t.id} key={t.id}>{t.name} ({t.id})</option>
                ))
              : <option value={currentUser?.tenant_id || 'default'}>
                  {currentUser?.tenant_id || 'default'}
                </option>
            }
          </select>
          <button type="submit" disabled={busy}>创建</button>
        </form>
        {message && <div className="status">{message}</div>}
      </section>

      <section className="panel">
        <div className="table-header">
          <h3>用户列表</h3>
          <span>{items.length} 个用户</span>
        </div>
        <div className="table user-table">
          <div className="table-row user-row table-head">
            <span>ID</span>
            <span>用户名</span>
            <span>租户</span>
            <span>状态</span>
            <span>创建时间</span>
          </div>
          {items.map((user) => (
            <div className="table-row user-row" key={user.id}>
              <span className="mono">{user.id}</span>
              <span>{user.username}</span>
              <span className="mono">{user.tenant_id}</span>
              <span>
                <button
                  className={user.enabled === false ? 'secondary' : 'danger'}
                  onClick={() => toggleUser(user.id, user.enabled === false)}
                  disabled={busy}
                >
                  {user.enabled === false ? '启用' : '禁用'}
                </button>
              </span>
              <span>{user.created_at || '-'}</span>
            </div>
          ))}
          {!items.length && <div className="empty">
            <p>暂无用户</p>
            <p style={{ fontSize: 13, marginTop: 4 }}>使用上方的表单创建第一个用户</p>
          </div>}
        </div>
      </section>
    </AdminLayout>
  )
}
