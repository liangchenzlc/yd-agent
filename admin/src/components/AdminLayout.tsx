import { useCallback, useEffect } from 'react'
import { useDispatch, useSelector } from 'react-redux'
import { NavLink, useNavigate } from 'react-router-dom'
import { api, type ApiUser } from '../api'
import { clearAuth, type RootState, setUser } from '../store'

type AdminLayoutProps = { children: React.ReactNode }

const superAdminNav = [
  { to: '/tenants', label: '租户管理', icon: 'M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z M9 22V12h6v10' },
  { to: '/admin-users', label: '管理员管理', icon: 'M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2 M9 3a4 4 0 1 0 0 8 4 4 0 0 0 0-8z' },
]

const adminNav = [
  { to: '/documents', label: '文档管理', icon: 'M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z M14 2v6h6 M16 13H8 M16 17H8 M10 9H8' },
  { to: '/qa-logs', label: '问答日志', icon: 'M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z M8 10h.01 M12 10h.01 M16 10h.01' },
  { to: '/hard-cases', label: '难例池', icon: 'M12 9v4 M12 17h.01 M10.29 3.86l-8.6 14.87A2 2 0 0 0 3.6 21h16.8a2 2 0 0 0 1.7-3.27l-8.6-14.87a2 2 0 0 0-3.21 0Z' },
  { to: '/knowledge-gaps', label: '知识缺口', icon: 'M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71 M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71' },
  { to: '/users', label: '用户管理', icon: 'M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2 M9 3a4 4 0 1 0 0 8 4 4 0 0 0 0-8z M23 21v-2a4 4 0 0 0-3-3.87 M16 3.13a4 4 0 0 1 0 7.75' },
  { to: '/data-sources', label: '数据源配置', icon: 'M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7 M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4 M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4' },
  { to: '/usage', label: '用量统计', icon: 'M22 12h-4l-3 9L9 3l-3 9H2' },
]

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
      dispatch(setUser(current))
    } catch { logout() }
  }, [dispatch, logout])

  useEffect(() => { loadMe() }, [loadMe])

  const isSuperAdmin = user?.role === 'super_admin'
  const navItems = isSuperAdmin
    ? [...adminNav, ...superAdminNav]
    : adminNav

  return (
    <div className="admin-layout">
      <aside className="admin-sidebar">
        <p className="eyebrow">yd-Agent Admin</p>
        <h1>管理后台</h1>
        <span className="pill">{user ? user.username : 'loading'}</span>
        {isSuperAdmin && <span className="pill super">超级管理员</span>}
        {navItems.map(({ to, label, icon }) => (
          <NavLink
            key={to}
            className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}
            to={to}
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ verticalAlign: 'middle', marginRight: 8 }}>
              <path d={icon} />
            </svg>
            {label}
          </NavLink>
        ))}
        <button className="secondary" onClick={logout}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ verticalAlign: 'middle', marginRight: 6 }}>
            <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
            <polyline points="16 17 21 12 16 7" />
            <line x1="21" y1="12" x2="9" y2="12" />
          </svg>
          退出登录
        </button>
      </aside>
      <main className="admin-main">{children}</main>
    </div>
  )
}
