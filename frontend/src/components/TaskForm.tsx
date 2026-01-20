import { useState } from 'react'
import { Send, GitBranch, FileText, Loader2 } from 'lucide-react'
import type { CreateTaskInput } from '../types'

interface TaskFormProps {
  onSubmit: (input: CreateTaskInput) => void
  isLoading?: boolean
}

export function TaskForm({ onSubmit, isLoading = false }: TaskFormProps) {
  const [task, setTask] = useState('')
  const [repository, setRepository] = useState('')
  const [context, setContext] = useState('')
  const [showAdvanced, setShowAdvanced] = useState(false)

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!task.trim() || isLoading) return
    
    onSubmit({
      task: task.trim(),
      repository: repository.trim() || undefined,
      context: context.trim() || undefined,
    })
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      {/* Main task input */}
      <div className="relative">
        <div className="absolute left-4 top-4 text-accent-cyan">
          <span className="font-mono text-sm">{'>'}</span>
        </div>
        <textarea
          value={task}
          onChange={(e) => setTask(e.target.value)}
          placeholder="Опишите задачу для команды агентов..."
          className="w-full bg-midnight-900 border border-midnight-700 rounded-lg px-10 py-4 
                     text-midnight-100 placeholder-midnight-500 font-mono text-sm
                     focus:outline-none focus:border-accent-cyan focus:ring-1 focus:ring-accent-cyan
                     resize-none min-h-[120px]"
          disabled={isLoading}
        />
        <div className="absolute right-4 bottom-4">
          <button
            type="submit"
            disabled={!task.trim() || isLoading}
            className="bg-gradient-accent text-midnight-950 px-4 py-2 rounded-lg font-mono font-medium
                       flex items-center gap-2 hover:opacity-90 transition-opacity
                       disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isLoading ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Send className="w-4 h-4" />
            )}
            {isLoading ? 'Запуск...' : 'Запустить'}
          </button>
        </div>
      </div>

      {/* Advanced options toggle */}
      <button
        type="button"
        onClick={() => setShowAdvanced(!showAdvanced)}
        className="text-midnight-400 hover:text-accent-cyan text-sm font-mono flex items-center gap-2"
      >
        <span className="text-accent-cyan">{showAdvanced ? '[-]' : '[+]'}</span>
        Дополнительные параметры
      </button>

      {/* Advanced options */}
      {showAdvanced && (
        <div className="space-y-4 p-4 bg-midnight-900/50 rounded-lg border border-midnight-800">
          {/* Repository */}
          <div>
            <label className="flex items-center gap-2 text-sm text-midnight-300 font-mono mb-2">
              <GitBranch className="w-4 h-4 text-accent-lime" />
              GitHub репозиторий (опционально)
            </label>
            <input
              type="text"
              value={repository}
              onChange={(e) => setRepository(e.target.value)}
              placeholder="owner/repo"
              className="w-full bg-midnight-900 border border-midnight-700 rounded-lg px-4 py-2
                         text-midnight-100 placeholder-midnight-500 font-mono text-sm
                         focus:outline-none focus:border-accent-cyan"
              disabled={isLoading}
            />
          </div>

          {/* Context */}
          <div>
            <label className="flex items-center gap-2 text-sm text-midnight-300 font-mono mb-2">
              <FileText className="w-4 h-4 text-accent-amber" />
              Дополнительный контекст
            </label>
            <textarea
              value={context}
              onChange={(e) => setContext(e.target.value)}
              placeholder="Технические ограничения, предпочтения, ссылки на документацию..."
              className="w-full bg-midnight-900 border border-midnight-700 rounded-lg px-4 py-3
                         text-midnight-100 placeholder-midnight-500 font-mono text-sm
                         focus:outline-none focus:border-accent-cyan resize-none min-h-[80px]"
              disabled={isLoading}
            />
          </div>
        </div>
      )}
    </form>
  )
}
