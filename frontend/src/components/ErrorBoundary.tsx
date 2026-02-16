import { Component } from 'react'
import type { ErrorInfo, ReactNode } from 'react'
import { AlertCircle, RefreshCw, LogOut } from 'lucide-react'
import { useAuthStore } from '../store/authStore'

interface Props {
  children: ReactNode
}

interface State {
  hasError: boolean
  error: Error | null
}

/**
 * React Error Boundary — catches render errors and displays a fallback UI.
 *
 * Class component is required because React does not yet support
 * error boundaries with hooks.
 */
class ErrorBoundaryInner extends Component<Props, State> {
  constructor(props: Props) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('[ErrorBoundary] Uncaught render error:', error, info.componentStack)
  }

  handleReload = () => {
    this.setState({ hasError: false, error: null })
    window.location.reload()
  }

  handleLogout = () => {
    useAuthStore.getState().logout()
    window.location.href = '/login'
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen bg-gradient-dark flex items-center justify-center px-4">
          <div className="max-w-md w-full bg-midnight-900/60 backdrop-blur-sm border border-midnight-700 rounded-2xl p-8 shadow-xl text-center">
            <div className="w-16 h-16 mx-auto mb-6 rounded-full bg-red-500/10 border border-red-500/30 flex items-center justify-center">
              <AlertCircle className="w-8 h-8 text-red-400" />
            </div>

            <h1 className="text-xl font-mono font-semibold text-midnight-100 mb-2">
              Что-то пошло не так
            </h1>
            <p className="text-midnight-400 text-sm font-mono mb-6">
              Произошла непредвиденная ошибка при отображении страницы.
            </p>

            {this.state.error && (
              <div className="mb-6 p-3 bg-midnight-800/80 border border-midnight-700 rounded-lg text-left">
                <p className="text-red-300/80 text-xs font-mono break-words">
                  {this.state.error.message}
                </p>
              </div>
            )}

            <div className="flex gap-3 justify-center">
              <button
                onClick={this.handleReload}
                className="flex items-center gap-2 px-4 py-2.5 bg-accent-cyan text-midnight-950 font-mono font-semibold rounded-xl hover:bg-accent-cyan/90 transition-all text-sm"
              >
                <RefreshCw className="w-4 h-4" />
                Перезагрузить
              </button>
              <button
                onClick={this.handleLogout}
                className="flex items-center gap-2 px-4 py-2.5 bg-midnight-800 border border-midnight-700 text-midnight-300 font-mono rounded-xl hover:border-midnight-600 transition-all text-sm"
              >
                <LogOut className="w-4 h-4" />
                Выйти
              </button>
            </div>
          </div>
        </div>
      )
    }

    return this.props.children
  }
}

export { ErrorBoundaryInner as ErrorBoundary }
