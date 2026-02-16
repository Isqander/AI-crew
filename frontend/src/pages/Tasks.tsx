import { useNavigate } from 'react-router-dom'
import { Activity, ArrowRight, Clock, CheckCircle, AlertCircle, Loader2, Search } from 'lucide-react'
import { ErrorBanner } from '../components/ErrorBanner'
import { useState, useMemo } from 'react'
import { useThreads } from '../hooks/useTask'
import type { Thread } from '../types'

type StatusFilter = 'all' | 'busy' | 'idle' | 'interrupted' | 'error'

const STATUS_CONFIG: Record<string, { label: string; icon: typeof Clock; color: string }> = {
  busy: { label: 'В работе', icon: Loader2, color: 'text-accent-cyan' },
  idle: { label: 'Завершена', icon: CheckCircle, color: 'text-accent-lime' },
  interrupted: { label: 'Ожидает ответа', icon: Clock, color: 'text-amber-400' },
  error: { label: 'Ошибка', icon: AlertCircle, color: 'text-red-400' },
}

function getStatusBadge(status: string) {
  const config = STATUS_CONFIG[status] || STATUS_CONFIG.idle
  const Icon = config.icon
  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-mono ${config.color} bg-current/10`}>
      <Icon className={`w-3 h-3 ${status === 'busy' ? 'animate-spin' : ''}`} />
      {config.label}
    </span>
  )
}

export function Tasks() {
  const navigate = useNavigate()
  const { data: threads, isLoading, error } = useThreads()
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all')

  const filteredThreads = useMemo(() => {
    if (!threads) return []
    return threads.filter((t: Thread) => {
      // Search filter
      const task = t.metadata?.task || ''
      const graphId = t.metadata?.graph_id || ''
      const matchesSearch = !search ||
        task.toLowerCase().includes(search.toLowerCase()) ||
        graphId.toLowerCase().includes(search.toLowerCase()) ||
        t.thread_id.toLowerCase().includes(search.toLowerCase())

      // Status filter
      const matchesStatus = statusFilter === 'all' || t.status === statusFilter

      return matchesSearch && matchesStatus
    })
  }, [threads, search, statusFilter])

  return (
    <div className="max-w-5xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div className="flex items-center gap-3">
          <Activity className="w-6 h-6 text-accent-cyan" />
          <h1 className="text-2xl font-mono font-semibold text-midnight-100">
            Задачи
          </h1>
          {threads && (
            <span className="text-midnight-500 font-mono text-sm">
              ({threads.length})
            </span>
          )}
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-4 mb-6">
        {/* Search */}
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-midnight-500" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Поиск по задачам..."
            className="w-full pl-10 pr-4 py-2.5 bg-midnight-900 border border-midnight-700 rounded-lg
                       text-midnight-200 font-mono text-sm placeholder-midnight-500
                       focus:border-accent-cyan/50 focus:outline-none transition-colors"
          />
        </div>

        {/* Status filter */}
        <div className="flex gap-2">
          {(['all', 'busy', 'idle', 'interrupted', 'error'] as StatusFilter[]).map((s) => (
            <button
              key={s}
              onClick={() => setStatusFilter(s)}
              className={`px-3 py-2 rounded-lg font-mono text-xs transition-colors border
                ${statusFilter === s
                  ? 'bg-accent-cyan/20 text-accent-cyan border-accent-cyan/40'
                  : 'bg-midnight-900 text-midnight-400 border-midnight-700 hover:border-midnight-600'
                }`}
            >
              {s === 'all' ? 'Все' : STATUS_CONFIG[s]?.label || s}
            </button>
          ))}
        </div>
      </div>

      {/* Loading */}
      {isLoading && (
        <div className="flex items-center justify-center h-64 text-midnight-400">
          <Loader2 className="w-6 h-6 animate-spin mr-2" />
          <span className="font-mono">Загрузка задач...</span>
        </div>
      )}

      {/* Error */}
      {error && (
        <ErrorBanner
          title="Ошибка загрузки"
          message={error.message}
          className="mb-6"
        />
      )}

      {/* Empty state */}
      {!isLoading && filteredThreads.length === 0 && (
        <div className="flex flex-col items-center justify-center h-64 text-midnight-500">
          <Activity className="w-12 h-12 mb-4 opacity-50" />
          <p className="font-mono text-lg mb-2">
            {search || statusFilter !== 'all' ? 'Задачи не найдены' : 'Пока нет задач'}
          </p>
          <p className="font-mono text-sm">
            {search || statusFilter !== 'all'
              ? 'Попробуйте изменить фильтры'
              : 'Создайте первую задачу на главной странице'}
          </p>
        </div>
      )}

      {/* Task list */}
      {!isLoading && filteredThreads.length > 0 && (
        <div className="space-y-2">
          {filteredThreads.map((t: Thread) => {
            const task = t.metadata?.task || 'Без названия'
            const graphId = t.metadata?.graph_id

            return (
              <button
                key={t.thread_id}
                onClick={() => navigate(`/task/${t.thread_id}`)}
                className="w-full bg-midnight-900 border border-midnight-800 rounded-lg p-4
                           hover:border-accent-cyan/50 transition-colors text-left
                           flex items-center justify-between group"
              >
                <div className="flex-1 min-w-0 mr-4">
                  <p className="font-mono text-midnight-200 text-sm truncate">
                    {task}
                  </p>
                  <div className="flex items-center gap-3 mt-2">
                    <span className="text-xs text-midnight-500 font-mono">
                      {new Date(t.created_at).toLocaleString('ru-RU')}
                    </span>
                    {graphId && (
                      <span className="px-2 py-0.5 bg-accent-cyan/10 text-accent-cyan text-xs font-mono rounded-full">
                        {graphId}
                      </span>
                    )}
                    <code className="text-xs text-midnight-600 font-mono">
                      {t.thread_id.slice(0, 8)}...
                    </code>
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  {getStatusBadge(t.status)}
                  <ArrowRight className="w-4 h-4 text-midnight-500 group-hover:text-accent-cyan transition-colors" />
                </div>
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}
