import { Navigate, Route, Routes } from 'react-router-dom'
import { DocumentsPage } from './pages/DocumentsPage'
import { HardCasesPage } from './pages/HardCasesPage'
import { KnowledgeGapsPage } from './pages/KnowledgeGapsPage'
import { LoginPage } from './pages/LoginPage'
import { QaLogsPage } from './pages/QaLogsPage'
import { UsersPage } from './pages/UsersPage'

function RequireAdmin({ children }: { children: React.ReactNode }) {
  const token = localStorage.getItem('yd_admin_token')
  return token ? children : <Navigate to="/login" replace />
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        path="/documents"
        element={
          <RequireAdmin>
            <DocumentsPage />
          </RequireAdmin>
        }
      />
      <Route
        path="/qa-logs"
        element={
          <RequireAdmin>
            <QaLogsPage />
          </RequireAdmin>
        }
      />
      <Route
        path="/hard-cases"
        element={
          <RequireAdmin>
            <HardCasesPage />
          </RequireAdmin>
        }
      />
      <Route
        path="/knowledge-gaps"
        element={
          <RequireAdmin>
            <KnowledgeGapsPage />
          </RequireAdmin>
        }
      />
      <Route
        path="/users"
        element={
          <RequireAdmin>
            <UsersPage />
          </RequireAdmin>
        }
      />
      <Route path="*" element={<Navigate to="/documents" replace />} />
    </Routes>
  )
}
