import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Bot, Mail, Lock, ArrowRight } from 'lucide-react'
import { useAuth } from '../hooks/useAuth'
import { ErrorBanner } from '../components/ErrorBanner'
import { FormInput } from '../components/FormInput'

export function Login() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const { login, loading, error } = useAuth()
  const navigate = useNavigate()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    try {
      await login(email, password)
      navigate('/')
    } catch {
      // Error is handled in useAuth
    }
  }

  return (
    <div className="min-h-screen bg-gradient-dark flex items-center justify-center px-4 py-12">
      <div className="w-full max-w-md">
        {/* Logo & Header */}
        <div className="text-center mb-10">
          <Link
            to="/"
            className="inline-flex items-center gap-3 group mb-6"
          >
            <div className="w-14 h-14 rounded-xl bg-gradient-accent flex items-center justify-center group-hover:glow-cyan transition-all shadow-lg">
              <Bot className="w-8 h-8 text-midnight-950" />
            </div>
            <div className="text-left">
              <h1 className="font-mono font-bold text-2xl text-accent-cyan">
                AI-crew
              </h1>
              <p className="text-sm text-midnight-400 font-mono">
                Мультиагентная платформа
              </p>
            </div>
          </Link>
          <h2 className="text-xl font-mono font-semibold text-midnight-100">
            Вход в систему
          </h2>
          <p className="text-midnight-400 text-sm mt-1 font-mono">
            Введите данные для входа
          </p>
        </div>

        {/* Form Card */}
        <div className="bg-midnight-900/60 backdrop-blur-sm border border-midnight-700 rounded-2xl p-8 shadow-xl shadow-midnight-950/50">
          <form onSubmit={handleSubmit} className="space-y-6">
            {error && <ErrorBanner message={error} />}

            <FormInput
              id="email"
              label="Email"
              type="email"
              icon={<Mail />}
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoComplete="email"
              placeholder="you@example.com"
            />

            <FormInput
              id="password"
              label="Пароль"
              type="password"
              icon={<Lock />}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              autoComplete="current-password"
              placeholder="••••••••"
            />

            <button
              type="submit"
              disabled={loading}
              className="w-full py-3 px-4 bg-accent-cyan text-midnight-950 font-mono font-semibold rounded-xl hover:bg-accent-cyan/90 focus:outline-none focus:ring-2 focus:ring-accent-cyan focus:ring-offset-2 focus:ring-offset-midnight-900 disabled:opacity-50 disabled:cursor-not-allowed transition-all flex items-center justify-center gap-2 group"
            >
              {loading ? (
                <span className="animate-pulse">Вход...</span>
              ) : (
                <>
                  Войти
                  <ArrowRight className="w-5 h-5 group-hover:translate-x-1 transition-transform" />
                </>
              )}
            </button>
          </form>

          <p className="mt-6 text-center text-midnight-400 text-sm font-mono">
            Нет аккаунта?{' '}
            <Link
              to="/register"
              className="text-accent-cyan hover:text-accent-cyan/80 font-medium transition-colors"
            >
              Зарегистрироваться
            </Link>
          </p>
        </div>
      </div>
    </div>
  )
}
