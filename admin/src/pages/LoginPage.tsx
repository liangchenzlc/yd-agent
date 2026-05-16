import { type FormEvent, useState } from 'react'
import { useDispatch } from 'react-redux'
import { useNavigate } from 'react-router-dom'
import { api, type ApiUser } from '../api'
import { setAuth } from '../store'

type AuthResponse = { token: string; user: ApiUser }

export function LoginPage() {
  const dispatch = useDispatch()
  const navigate = useNavigate()
  const [username, setUsername] = useState('admin')
  const [password, setPassword] = useState('admin')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError('')
    setBusy(true)
    try {
      const result = await api<AuthResponse>('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      })
      dispatch(setAuth(result))
      navigate('/documents', { replace: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : '登录失败')
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="login-shell">
      <form className="login-panel" onSubmit={onSubmit}>
        <p className="eyebrow">yd-Agent Admin</p>
        <h1>管理后台登录</h1>
        <label htmlFor="username">账号</label>
        <input
          id="username"
          value={username}
          onChange={(event) => setUsername(event.target.value)}
          autoFocus
        />
        <label htmlFor="password">密码</label>
        <input
          id="password"
          type="password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
        />
        <button type="submit" disabled={busy}>{busy ? '登录中...' : '登录'}</button>
        <div className="error">{error}</div>
      </form>
    </main>
  )
}
