import { useState } from 'react'
import { useAuthStore } from '../store/authStore'
import { aegraClient } from '../api/aegra'

export function useAuth() {
  const { setAuth, logout: clearAuth, isAuthenticated, user } = useAuthStore()
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const login = async (email: string, password: string) => {
    setLoading(true)
    setError(null)
    try {
      const data = await aegraClient.login(email, password)
      setAuth(data.user, data.access_token, data.refresh_token)
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Login failed'
      setError(message)
      throw err
    } finally {
      setLoading(false)
    }
  }

  const register = async (email: string, password: string, displayName: string) => {
    setLoading(true)
    setError(null)
    try {
      const data = await aegraClient.register(email, password, displayName)
      setAuth(data.user, data.access_token, data.refresh_token)
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Registration failed'
      setError(message)
      throw err
    } finally {
      setLoading(false)
    }
  }

  const logout = () => {
    clearAuth()
  }

  return { login, register, logout, loading, error, isAuthenticated, user }
}
