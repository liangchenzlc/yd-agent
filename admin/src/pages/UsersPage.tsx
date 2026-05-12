import { type FormEvent, useCallback, useEffect, useState } from 'react'
import { useDispatch, useSelector } from 'react-redux'
import { api, type ApiUser } from '../api'
import { AdminLayout } from '../components/AdminLayout'
import { type RootState, setUsers } from '../store'

const roles = ['employee', 'admin', 'super_admin']

export function UsersPage() {
  const dispatch = useDispatch()
  const { items } = useSelector((state: RootState) => state.users)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [role, setRole] = useState('employee')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)

  const loadUsers = useCallback(async () => {
    dispatch(setUsers(await api<ApiUser[]>('/api/admin/users')))
  }, [dispatch])

  useEffect(() => {
    const timer = window.setTimeout(() => {
      loadUsers()
    }, 0)
    return () => window.clearTimeout(timer)
  }, [loadUsers])

  async function createUser(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setBusy(true)
    setMessage('正在创建用户...')
    try {
      await api('/api/admin/users', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password, role }),
      })
      setUsername('')
      setPassword('')
      setRole('employee')
      setMessage('用户已创建')
      await loadUsers()
    } catch (err) {
      setMessage(err instanceof Error ? err.message : '创建用户失败')
    } finally {
      setBusy(false)
    }
  }

  async function updateUser(userId: number, next: Partial<Pick<ApiUser, 'role' | 'enabled'>>) {
    setBusy(true)
    setMessage('正在更新用户...')
    try {
      await api(`/api/admin/users/${userId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(next),
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
          <select value={role} onChange={(event) => setRole(event.target.value)}>
            {roles.map((item) => (
              <option value={item} key={item}>{item}</option>
            ))}
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
            <span>角色</span>
            <span>状态</span>
            <span>创建时间</span>
          </div>
          {items.map((user) => (
            <div className="table-row user-row" key={user.id}>
              <span className="mono">{user.id}</span>
              <span>{user.username}</span>
              <span>
                <select
                  value={user.role}
                  onChange={(event) => updateUser(user.id, { role: event.target.value })}
                  disabled={busy}
                >
                  {roles.map((item) => (
                    <option value={item} key={item}>{item}</option>
                  ))}
                </select>
              </span>
              <span>
                <button
                  className={user.enabled === false ? 'secondary' : 'danger'}
                  onClick={() => updateUser(user.id, { enabled: !(user.enabled ?? true) })}
                  disabled={busy}
                >
                  {user.enabled === false ? '启用' : '禁用'}
                </button>
              </span>
              <span>{user.created_at || '-'}</span>
            </div>
          ))}
          {!items.length && <div className="empty">暂无用户</div>}
        </div>
      </section>
    </AdminLayout>
  )
}
