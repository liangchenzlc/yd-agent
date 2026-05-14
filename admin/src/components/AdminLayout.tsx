import { useCallback, useEffect } from 'react'
import { useDispatch, useSelector } from 'react-redux'
import { NavLink, useNavigate } from 'react-router-dom'
import { api, type ApiUser } from '../api'
import { clearAuth, type RootState, setUser } from '../store'

type AdminLayoutProps = {
  children: React.ReactNode
}

export function AdminLayout({ children }: AdminLayoutProps) {
  const dispatch = useDispatch()
  const navigate = useNavigate()
  const { user } = useSelector((state: RootState) => state.auth)

  const logout = useCallback(() => {
    dispatch(clearAuth())
    navigate('/login', { replace: true })
  }, [dispatch, navigate])

  const loadMe = useCallback(async () => {
    try {
      const current = await api<ApiUser>('/api/me')
      if (!['admin', 'super_admin'].includes(current.role)) {
        logout()
        return
      }
      dispatch(setUser(current))
    } catch {
      logout()
    }
  }, [dispatch, logout])

  useEffect(() => {
    loadMe()
  }, [loadMe])

  return (
    <div className="admin-layout">
      <aside className="admin-sidebar">
        <p className="eyebrow">yd-Agent Admin</p>
        <h1>管理后台</h1>
        <span className="pill">{user ? `${user.username} · ${user.role}` : 'loading'}</span>
        <NavLink className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`} to="/documents">
          文档管理
        </NavLink>
        <NavLink className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`} to="/qa-logs">
          问答日志
        </NavLink>
        <NavLink className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`} to="/hard-cases">
          难例池
        </NavLink>
        <NavLink className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`} to="/knowledge-gaps">
          知识缺口
        </NavLink>
        <NavLink className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`} to="/users">
          用户管理
        </NavLink>
        <NavLink className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`} to="/usage">
          用量统计
        </NavLink>
        <button className="secondary" onClick={logout}>
          退出登录
        </button>
      </aside>
      <main className="admin-main">{children}</main>
    </div>
  )
}
