import { type FormEvent, useCallback, useEffect, useState } from 'react'
import { useSelector } from 'react-redux'
import { api, type ApiTenant, type DataSourceConfig } from '../api'
import { AdminLayout } from '../components/AdminLayout'
import { type RootState } from '../store'

type DbType = 'mysql' | 'postgresql' | 'sqlite'

type FormData = {
  db_type: DbType
  db_host: string
  db_port: string
  db_user: string
  db_password: string
  db_database: string
}

const EMPTY_FORM: FormData = {
  db_type: 'mysql',
  db_host: '',
  db_port: '',
  db_user: '',
  db_password: '',
  db_database: '',
}

const DEFAULT_PORTS: Record<DbType, string> = {
  mysql: '3306',
  postgresql: '5432',
  sqlite: '',
}

const DB_LABELS: Record<DbType, string> = {
  mysql: 'MySQL',
  postgresql: 'PostgreSQL',
  sqlite: 'SQLite',
}

const DB_ICONS: Record<DbType, string> = {
  mysql: 'M',
  postgresql: 'Pg',
  sqlite: 'SL',
}

function dbConfigToForm(ds: DataSourceConfig): FormData {
  return {
    db_type: ds.db_type as DbType,
    db_host: ds.db_host,
    db_port: ds.db_port != null ? String(ds.db_port) : '',
    db_user: ds.db_user,
    db_password: ds.db_password,
    db_database: ds.db_database,
  }
}

export function DataSourcesPage() {
  const { user } = useSelector((state: RootState) => state.auth)
  const isSuperAdmin = user?.role === 'super_admin'

  const [tenants, setTenants] = useState<ApiTenant[]>([])
  const [selectedTenant, setSelectedTenant] = useState('')
  const [config, setConfig] = useState<DataSourceConfig | null>(null)
  const [form, setForm] = useState<FormData>(EMPTY_FORM)
  const [message, setMessage] = useState<{ text: string; type: 'info' | 'success' | 'error' } | null>(null)
  const [busy, setBusy] = useState(false)

  // Load tenant list for super_admin
  useEffect(() => {
    if (isSuperAdmin) {
      api<ApiTenant[]>('/api/admin/tenants').then(setTenants).catch(() => {})
    }
  }, [isSuperAdmin])

  const resolvedTenant = isSuperAdmin ? selectedTenant : (user?.tenant_id || '')

  // Load data source config
  const loadConfig = useCallback(async () => {
    if (!resolvedTenant) {
      setConfig(null)
      setForm(EMPTY_FORM)
      return
    }
    try {
      const ds = await api<DataSourceConfig | null>(`/api/admin/data-sources?tenant_id=${resolvedTenant}`)
      setConfig(ds)
      setForm(ds ? dbConfigToForm(ds) : { ...EMPTY_FORM, db_type: 'mysql' })
    } catch {
      setConfig(null)
      setForm({ ...EMPTY_FORM, db_type: 'mysql' })
    }
  }, [resolvedTenant])

  useEffect(() => { loadConfig() }, [loadConfig])

  function setDbType(db_type: DbType) {
    setForm((prev) => ({
      ...prev,
      db_type,
      db_port: prev.db_port || DEFAULT_PORTS[db_type],
    }))
  }

  // Save
  async function saveConfig(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setBusy(true)
    setMessage({ text: '正在保存...', type: 'info' })
    try {
      const body = {
        db_type: form.db_type,
        db_host: form.db_host,
        db_port: form.db_port ? Number(form.db_port) : null,
        db_user: form.db_user,
        db_password: form.db_password,
        db_database: form.db_database,
      }
      const params = isSuperAdmin ? `?tenant_id=${selectedTenant}` : ''
      const result = await api<DataSourceConfig>(`/api/admin/data-sources${params}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      setConfig(result)
      setMessage({ text: '数据源配置已保存', type: 'success' })
    } catch (err) {
      setMessage({ text: err instanceof Error ? err.message : '保存失败', type: 'error' })
    } finally {
      setBusy(false)
    }
  }

  // Test connection
  async function testConnection() {
    setBusy(true)
    setMessage({ text: '正在测试连接...', type: 'info' })
    try {
      const body = {
        db_type: form.db_type,
        db_host: form.db_host,
        db_port: form.db_port ? Number(form.db_port) : null,
        db_user: form.db_user,
        db_password: form.db_password,
        db_database: form.db_database,
      }
      const result = await api<{ ok: boolean; message: string }>('/api/admin/data-sources/test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      setMessage({ text: result.message, type: result.ok ? 'success' : 'error' })
    } catch (err) {
      setMessage({ text: err instanceof Error ? err.message : '测试失败', type: 'error' })
    } finally {
      setBusy(false)
    }
  }

  // Delete
  async function deleteConfig() {
    if (!window.confirm('确定删除数据源配置？')) return
    setBusy(true)
    setMessage({ text: '正在删除...', type: 'info' })
    try {
      const params = isSuperAdmin ? `?tenant_id=${selectedTenant}` : ''
      await api(`/api/admin/data-sources${params}`, { method: 'DELETE' })
      setConfig(null)
      setForm({ ...EMPTY_FORM, db_type: 'mysql' })
      setMessage({ text: '数据源已删除', type: 'success' })
    } catch (err) {
      setMessage({ text: err instanceof Error ? err.message : '删除失败', type: 'error' })
    } finally {
      setBusy(false)
    }
  }

  return (
    <AdminLayout>
      <header className="page-header">
        <div>
          <p className="eyebrow">Data Sources</p>
          <h2>数据源配置</h2>
        </div>
        {config && resolvedTenant && (
          <button className="secondary compact" onClick={loadConfig} disabled={busy}>
            刷新
          </button>
        )}
      </header>

      {/* Tenant selector — super_admin only */}
      {isSuperAdmin && (
        <section className="panel" style={{ padding: 16 }}>
          <label style={{ fontSize: 13, color: 'var(--muted)', marginBottom: 6, display: 'block' }}>
            选择租户
          </label>
          <select
            value={selectedTenant}
            onChange={(e) => setSelectedTenant(e.target.value)}
            style={{ maxWidth: 360 }}
          >
            <option value="">— 请选择租户 —</option>
            {tenants.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name} ({t.id})
              </option>
            ))}
          </select>
        </section>
      )}

      {!resolvedTenant && (
        <section className="panel">
          <div className="empty">
            <p>{isSuperAdmin ? '请先选择一个租户' : '当前管理员没有关联租户'}</p>
          </div>
        </section>
      )}

      {resolvedTenant && (
        <section className="panel" style={{ padding: 0, overflow: 'hidden' }}>
          {/* Header */}
          <div style={{ padding: '20px 24px', borderBottom: '1px solid var(--border)' }}>
            <h3 style={{ margin: 0, fontSize: 16, fontWeight: 600 }}>
              {config ? '编辑数据源' : '配置数据源'}
            </h3>
            <p className="muted" style={{ marginTop: 4, marginBottom: 0 }}>
              配置该租户下的数据库连接，用于 Text-to-SQL 数据分析和图表生成
            </p>
          </div>

          {/* Database type selector — visual cards */}
          <div style={{ padding: '20px 24px', borderBottom: '1px solid var(--border)' }}>
            <label style={{ fontSize: 13, fontWeight: 500, color: 'var(--primary)', marginBottom: 10, display: 'block' }}>
              数据库类型
            </label>
            <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
              {(['mysql', 'postgresql', 'sqlite'] as const).map((type) => {
                const active = form.db_type === type
                return (
                  <button
                    key={type}
                    type="button"
                    onClick={() => setDbType(type)}
                    disabled={busy}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 10,
                      padding: '12px 20px',
                      borderRadius: 8,
                      border: active ? '2px solid var(--cta)' : '2px solid var(--border)',
                      background: active ? '#eff6ff' : '#fff',
                      color: active ? 'var(--cta)' : 'var(--muted)',
                      fontWeight: active ? 600 : 400,
                      cursor: 'pointer',
                      fontSize: 14,
                      transition: 'all 150ms ease',
                      minWidth: 140,
                      justifyContent: 'center',
                    }}
                  >
                    <span
                      style={{
                        display: 'inline-flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        width: 32,
                        height: 32,
                        borderRadius: 6,
                        background: active ? 'var(--cta)' : '#f1f5f9',
                        color: active ? '#fff' : 'var(--muted)',
                        fontWeight: 700,
                        fontSize: 12,
                        fontFamily: 'var(--font-mono)',
                      }}
                    >
                      {DB_ICONS[type]}
                    </span>
                    {DB_LABELS[type]}
                  </button>
                )
              })}
            </div>
          </div>

          {/* Form fields */}
          <form onSubmit={saveConfig} style={{ padding: '20px 24px' }}>
            {form.db_type !== 'sqlite' ? (
              <>
                {/* MySQL / PostgreSQL form — 2-column grid */}
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
                  <div>
                    <label style={labelStyle}>主机地址</label>
                    <input
                      value={form.db_host}
                      placeholder="例如：192.168.1.100 或 db.example.com"
                      onChange={(e) => setForm({ ...form, db_host: e.target.value })}
                      required
                    />
                  </div>
                  <div>
                    <label style={labelStyle}>
                      端口
                      <span style={{ color: 'var(--muted)', fontWeight: 400, fontSize: 12, marginLeft: 6 }}>
                        (默认 {DEFAULT_PORTS[form.db_type]})
                      </span>
                    </label>
                    <input
                      value={form.db_port}
                      placeholder={DEFAULT_PORTS[form.db_type]}
                      onChange={(e) => setForm({ ...form, db_port: e.target.value })}
                    />
                  </div>
                  <div>
                    <label style={labelStyle}>用户名</label>
                    <input
                      value={form.db_user}
                      placeholder="数据库登录用户名"
                      onChange={(e) => setForm({ ...form, db_user: e.target.value })}
                    />
                  </div>
                  <div>
                    <label style={labelStyle}>密码</label>
                    <input
                      value={form.db_password}
                      type="password"
                      placeholder="数据库登录密码"
                      onChange={(e) => setForm({ ...form, db_password: e.target.value })}
                    />
                  </div>
                  <div style={{ gridColumn: '1 / -1' }}>
                    <label style={labelStyle}>数据库名</label>
                    <input
                      value={form.db_database}
                      placeholder={
                        form.db_type === 'mysql'
                          ? '例如：my_database'
                          : '例如：my_database'
                      }
                      onChange={(e) => setForm({ ...form, db_database: e.target.value })}
                      required
                    />
                  </div>
                </div>
              </>
            ) : (
              /* SQLite form — single prominent input */
              <div>
                <div
                  style={{
                    border: '2px dashed var(--border)',
                    borderRadius: 10,
                    padding: 24,
                    background: '#fafbfc',
                    textAlign: 'center',
                  }}
                >
                  <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--primary)', marginBottom: 12 }}>
                    SQLite 数据库文件
                  </div>
                  <input
                    value={form.db_database}
                    placeholder="例如：/data/my_database.db"
                    onChange={(e) => setForm({ ...form, db_database: e.target.value })}
                    required
                    style={{
                      fontFamily: 'var(--font-mono)',
                      fontSize: 14,
                      textAlign: 'center',
                      maxWidth: 520,
                      margin: '0 auto',
                    }}
                  />
                  <p className="muted" style={{ marginTop: 10, marginBottom: 0 }}>
                    请输入 SQLite 数据库文件的绝对路径
                  </p>
                </div>
              </div>
            )}

            {/* Action buttons */}
            <div
              style={{
                display: 'flex',
                gap: 10,
                marginTop: 20,
                paddingTop: 16,
                borderTop: '1px solid var(--border)',
              }}
            >
              <button type="submit" disabled={busy}>
                保存配置
              </button>
              <button type="button" className="secondary compact" onClick={testConnection} disabled={busy}>
                测试连接
              </button>
              {config && (
                <button type="button" className="danger compact" onClick={deleteConfig} disabled={busy}>
                  删除配置
                </button>
              )}
            </div>
          </form>

          {/* Status message */}
          {message && (
            <div
              style={{
                margin: '0 24px 20px',
                padding: '10px 14px',
                borderRadius: 6,
                fontSize: 13,
                border: '1px solid',
                background:
                  message.type === 'success' ? '#f0fdf4' :
                  message.type === 'error' ? '#fef2f2' :
                  '#f8fafc',
                borderColor:
                  message.type === 'success' ? '#bbf7d0' :
                  message.type === 'error' ? '#fecaca' :
                  'var(--border)',
                color:
                  message.type === 'success' ? 'var(--success)' :
                  message.type === 'error' ? 'var(--danger)' :
                  'var(--muted)',
              }}
            >
              {message.type === 'success' && '✓ '}
              {message.type === 'error' && '✗ '}
              {message.text}
            </div>
          )}
        </section>
      )}

      {/* Current config display */}
      {config && resolvedTenant && (
        <section className="panel">
          <h3>当前配置概览</h3>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))',
              gap: 16,
              marginTop: 14,
            }}
          >
            {[
              { label: '数据库类型', value: <span className="pill">{config.db_type}</span> },
              { label: '主机地址', value: config.db_host || '-' },
              { label: '端口', value: config.db_port ?? '-' },
              { label: '用户名', value: config.db_user || '-', mono: false },
              { label: '数据库名', value: config.db_database, mono: true },
              { label: '更新时间', value: config.updated_at },
            ].map((item) => (
              <div key={item.label}>
                <div style={{ fontSize: 12, color: 'var(--muted)', marginBottom: 4 }}>{item.label}</div>
                <div
                  style={{
                    fontSize: 14,
                    fontWeight: 500,
                    fontFamily: item.mono ? 'var(--font-mono)' : undefined,
                    wordBreak: 'break-all',
                  }}
                >
                  {item.value}
                </div>
              </div>
            ))}
          </div>
        </section>
      )}
    </AdminLayout>
  )
}

const labelStyle: React.CSSProperties = {
  display: 'block',
  fontSize: 13,
  fontWeight: 500,
  color: 'var(--primary)',
  marginBottom: 6,
}
