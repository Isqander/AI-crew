import { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { Bot, Home, Activity, Settings } from 'lucide-react'

interface LayoutProps {
  children: ReactNode
}

export function Layout({ children }: LayoutProps) {
  return (
    <div className="min-h-screen bg-gradient-dark">
      {/* Header */}
      <header className="border-b border-midnight-800 bg-midnight-950/80 backdrop-blur-sm sticky top-0 z-50">
        <div className="container mx-auto px-4 py-4 flex items-center justify-between">
          <Link to="/" className="flex items-center gap-3 group">
            <div className="w-10 h-10 rounded-lg bg-gradient-accent flex items-center justify-center group-hover:glow-cyan transition-all">
              <Bot className="w-6 h-6 text-midnight-950" />
            </div>
            <div>
              <h1 className="font-mono font-semibold text-lg text-accent-cyan">
                AI-crew
              </h1>
              <p className="text-xs text-midnight-400 font-mono">
                Мультиагентная платформа
              </p>
            </div>
          </Link>
          
          <nav className="flex items-center gap-6">
            <NavLink to="/" icon={<Home className="w-4 h-4" />}>
              Главная
            </NavLink>
            <NavLink to="/tasks" icon={<Activity className="w-4 h-4" />}>
              Задачи
            </NavLink>
            <NavLink to="/settings" icon={<Settings className="w-4 h-4" />}>
              Настройки
            </NavLink>
          </nav>
        </div>
      </header>

      {/* Main content */}
      <main className="container mx-auto px-4 py-8">
        {children}
      </main>

      {/* Footer */}
      <footer className="border-t border-midnight-800 mt-auto">
        <div className="container mx-auto px-4 py-4 text-center text-midnight-500 text-sm font-mono">
          <p>
            Powered by{' '}
            <span className="text-accent-cyan">LangGraph</span>
            {' + '}
            <span className="text-accent-magenta">Aegra</span>
          </p>
        </div>
      </footer>
    </div>
  )
}

interface NavLinkProps {
  to: string
  icon: ReactNode
  children: ReactNode
}

function NavLink({ to, icon, children }: NavLinkProps) {
  return (
    <Link 
      to={to}
      className="flex items-center gap-2 text-midnight-300 hover:text-accent-cyan transition-colors font-mono text-sm"
    >
      {icon}
      {children}
    </Link>
  )
}
