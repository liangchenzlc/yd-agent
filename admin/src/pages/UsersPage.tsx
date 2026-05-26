import { type FormEvent, useCallback, useEffect, useState } from 'react'
import { useDispatch, useSelector } from 'react-redux'
import { api, type ApiUser } from '../api'
import { AdminLayout } from '../components/AdminLayout'
import { type RootState, setUsers } from '../store'

export function UsersPage() {
  const dispatch = useDispatch()
  const { items } = useSelector((state: RootState) => state.users)
  const { user: currentUser } = useSelector((state: RootState) => state.auth)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [tenantId, setTenantId] = useState('')
  const [tenants, setTenants] = useState<Array<{ id: string; name: string }>>([])
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)

  const isSuperAdmin = currentUser?.role === 'super_admin'

  // 如果是 super_admin，加载租户列表用于创建 admin 时选择
  useEffect(() => {
    if (isSuperAdmin) {
      api<Array<{ id: string; name: string }>>('/api/admin/tenants').then(setTenants).catch(() => {})
    }
  }, [isSuperAdmin])

  const loadUsers = useCallback(async () => {
    // super_admin 查看 admin 列表，admin 查看 user 列表
    const endpoint = isSuperAdmin ? '/api/admin/admin-users' : '/api/admin/users'
    dispatch(setUsers(await api<ApiUser[]>(endpoint)))
  }, [dispatch, isSuperAdmin])

  useEffect(() => {
    const timer = window.setTimeout(() => loadUsers(), 0)
    return () => window.clearTimeout(timer)
  }, [loadUsers])

  async function createUser(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setBusy(true)
    setMessage(isSuperAdmin ? '正在创建管理员...' : '正在创建用户...')
    try {
      if (isSuperAdmin) {
        // 创建 admin（需要指定租户）
        await api('/api/admin/admin-users', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ username, password, tenant_id: tenantId }),
        })
      } else {
        // 创建 user（使用当前 admin 的租户）
        await api('/api/admin/users', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ username, password }),
        })
      }
      setUsername('')
      setPassword('')
      setTenantId('')
      setMessage(isSuperAdmin ? '管理员已创建' : '用户已创建')
      await loadUsers()
    } catch (err) {
      setMessage(err instanceof Error ? err.message : '创建失败')
    } finally {
      setBusy(false)
    }
  }

  async function toggleUser(userId: number, enabled: boolean) {
    setBusy(true)
    setMessage('正在更新...')
    try {
      const endpoint = isSuperAdmin ? `/api/admin/admin-users/${userId}` : `/api/admin/users/${userId}`
      await api(endpoint, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled }),
      })
      setMessage('已更新')
      await loadUsers()
    } catch (err) {
      setMessage(err instanceof Error ? err.message : '更新失败')
    } finally {
      setBusy(false)
    }
  }

  async function resetPassword(userId: number) {
    const newPw = window.prompt('请输入新密码：')
    if (!newPw) return
    setBusy(true)
    try {
      const endpoint = isSuperAdmin ? `/api/admin/admin-users/${userId}/reset-password` : `/api/admin/users/${userId}/reset-password`
      await api(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ new_password: newPw }),
      })
      setMessage('密码已重置')
    } catch (err) {
      setMessage(err instanceof Error ? err.message : '重置失败')
    } finally {
      setBusy(false)
    }
  }

  async function deleteUser(userId: number) {
    if (!window.confirm('确定删除该账号？')) return
    setBusy(true)
    try {
      await api(`/api/admin/admin-users/${userId}`, { method: 'DELETE' })
      setMessage('已删除')
      await loadUsers()
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
          <p className="eyebrow">{isSuperAdmin ? 'Admins' : 'Users'}</p>
          <h2>{isSuperAdmin ? '管理员管理' : '用户管理'}</h2>
        </div>
        <button onClick={loadUsers} disabled={busy}>刷新</button>
      </header>

      <section className="panel">
        <h3>{isSuperAdmin ? '创建管理员' : '创建用户'}</h3>
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
          {isSuperAdmin && (
            <select value={tenantId} onChange={(event) => setTenantId(event.target.value)} required>
              <option value="">选择所属租户</option>
              {tenants.map((t) => (
                <option value={t.id} key={t.id}>{t.name} ({t.id})</option>
              ))}
            </select>
          )}
          <button type="submit" disabled={busy || (isSuperAdmin && !tenantId)}>
            {isSuperAdmin ? '创建管理员' : '创建用户'}
          </button>
        </form>
        {message && <div className="status">{message}</div>}
      </section>

      <section className="panel">
        <div className="table-header">
          <h3>{isSuperAdmin ? '管理员列表' : '用户列表'}</h3>
          <span>{items.length} {isSuperAdmin ? '个管理员' : '个用户'}</span>
        </div>
        <div className="table user-table">
          <div className="table-row user-row table-head">
            <span>ID</span>
            <span>用户名</span>
            <span>角色</span>
            {isSuperAdmin && <span>所属租户</span>}
            <span>状态</span>
            <span>操作</span>
          </div>
          {items.map((u) => (
            <div className="table-row user-row" key={u.id}>
              <span className="mono">{u.id}</span>
              <span>{u.username}</span>
              <span>{u.role}</span>
              {isSuperAdmin && <span className="mono">{u.tenant_id || '-'}</span>}
              <span>
                <button
                  className={u.enabled === false ? 'secondary' : 'danger'}
                  onClick={() => toggleUser(u.id, u.enabled === false)}
                  disabled={busy}
                >
                  {u.enabled === false ? '启用' : '禁用'}
                </button>
              </span>
              <span style={{ display: 'flex', gap: 8 }}>
                <button className="compact" onClick={() => resetPassword(u.id)} disabled={busy}>重置密码</button>
                {isSuperAdmin && (
                  <button className="danger compact" onClick={() => deleteUser(u.id)} disabled={busy}>删除</button>
                )}
              </span>
            </div>
          ))}
          {!items.length && <div className="empty"><p>暂无数据</p></div>}
        </div>
      </section>
    </AdminLayout>
  )
}
