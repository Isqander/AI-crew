import { BrowserRouter, Routes, Route, Navigate, Outlet } from 'react-router-dom'
import { useAuthStore } from './store/authStore'
import { Home } from './pages/Home'
import { TaskDetail } from './pages/TaskDetail'
import { Tasks } from './pages/Tasks'
import { Settings } from './pages/Settings'
import { Login } from './pages/Login'
import { Register } from './pages/Register'
import { Layout } from './components/Layout'
import { ErrorBoundary } from './components/ErrorBoundary'

function ProtectedRoute() {
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated)
  if (!isAuthenticated) {
    return <Navigate to="/login" replace />
  }
  return <Outlet />
}

function App() {
  return (
    <ErrorBoundary>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
          <Route element={<ProtectedRoute />}>
            <Route element={<Layout><Outlet /></Layout>}>
              <Route path="/" element={<Home />} />
              <Route path="/tasks" element={<Tasks />} />
              <Route path="/settings" element={<Settings />} />
              <Route path="/task/:threadId" element={<TaskDetail />} />
            </Route>
          </Route>
        </Routes>
      </BrowserRouter>
    </ErrorBoundary>
  )
}

export default App
