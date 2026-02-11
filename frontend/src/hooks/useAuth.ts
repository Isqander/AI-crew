import { useState } from 'react'
import { useAuthStore } from '../store/authStore'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8080'

export function useAuth() {
  const { setAuth, logout: clearAuth, isAuthenticated, user } = useAuthStore()
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const login = async (email: string, password: string) => {
    setLoading(true)
    setError(null)
    try {
      const resp = await fetch(`${API_URL}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      })
      if (!resp.ok) {
        const data = await resp.json()
        throw new Error(data.detail || 'Login failed')
      }
      const data = await resp.json()
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
      const resp = await fetch(`${API_URL}/auth/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password, display_name: displayName }),
      })
      if (!resp.ok) {
        const data = await resp.json()
        throw new Error(data.detail || 'Registration failed')
      }
      const data = await resp.json()
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
