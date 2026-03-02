import { useState, useEffect } from 'react'
import { Send, GitBranch, FileText, Loader2, Cpu, ChevronDown } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { CreateTaskInput, GraphListItem } from '../types'
import { aegraClient } from '../api/aegra'

interface TaskFormProps {
  onSubmit: (input: CreateTaskInput) => void
  isLoading?: boolean
}

const LLM_AUTO_VALUE = '__llm_auto__'

export function TaskForm({ onSubmit, isLoading = false }: TaskFormProps) {
  const [task, setTask] = useState('')
  const [repository, setRepository] = useState('')
  const [context, setContext] = useState('')
  const [graphId, setGraphId] = useState<string>(LLM_AUTO_VALUE)
  const [graphs, setGraphs] = useState<GraphListItem[]>([])
  const [graphsLoading, setGraphsLoading] = useState(true)
  const [showAdvanced, setShowAdvanced] = useState(false)
  const { t } = useTranslation()

  useEffect(() => {
    let cancelled = false
    async function loadGraphs() {
      try {
        const list = await aegraClient.getGraphList()
        if (!cancelled) {
          setGraphs(list)
        }
      } catch (err) {
        console.warn('Failed to load graphs:', err)
      } finally {
        if (!cancelled) setGraphsLoading(false)
      }
    }
    loadGraphs()
    return () => { cancelled = true }
  }, [])

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!task.trim() || isLoading) return
    
    onSubmit({
      task: task.trim(),
      repository: repository.trim() || undefined,
      context: context.trim() || undefined,
      graph_id: graphId === LLM_AUTO_VALUE ? undefined : graphId,
    })
  }

  const selectedGraph = graphs.find(g => g.graph_id === graphId)

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
          placeholder={t('taskForm.placeholder')}
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
            {isLoading ? t('taskForm.launching') : t('taskForm.launch')}
          </button>
        </div>
      </div>

      {/* Graph selection */}
      <div>
        <label className="flex items-center gap-2 text-sm text-midnight-300 font-mono mb-2">
          <Cpu className="w-4 h-4 text-accent-magenta" />
          {t('taskForm.graphSelect')}
        </label>
        <div className="relative">
          <select
            value={graphId}
            onChange={(e) => setGraphId(e.target.value)}
            className="w-full bg-midnight-900 border border-midnight-700 rounded-lg px-4 py-3
                       text-midnight-100 font-mono text-sm appearance-none cursor-pointer
                       focus:outline-none focus:border-accent-cyan focus:ring-1 focus:ring-accent-cyan
                       disabled:opacity-50"
            disabled={isLoading || graphsLoading}
          >
            <option value={LLM_AUTO_VALUE}>
              🤖 {t('taskForm.llmAuto')}
            </option>
            {graphs.map((g) => (
              <option key={g.graph_id} value={g.graph_id}>
                {g.display_name} — {g.description.slice(0, 60)}
                {g.description.length > 60 ? '...' : ''}
              </option>
            ))}
          </select>
          <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-midnight-400 pointer-events-none" />
        </div>

        {graphId !== LLM_AUTO_VALUE && selectedGraph && (
          <div className="mt-2 p-3 bg-midnight-900/50 rounded-lg border border-midnight-800 text-xs font-mono">
            <div className="text-accent-cyan mb-1">{selectedGraph.display_name} v{selectedGraph.version}</div>
            <div className="text-midnight-400 mb-1">{selectedGraph.description}</div>
            <div className="flex flex-wrap gap-1 mt-1">
              {selectedGraph.agents.map((a) => (
                <span key={a.id} className="bg-midnight-800 text-midnight-300 px-2 py-0.5 rounded">
                  {a.display_name}
                </span>
              ))}
            </div>
          </div>
        )}

        {graphId === LLM_AUTO_VALUE && (
          <p className="text-xs text-midnight-500 font-mono mt-1">
            {t('taskForm.llmAutoHint')}
          </p>
        )}
      </div>

      {/* Advanced options toggle */}
      <button
        type="button"
        onClick={() => setShowAdvanced(!showAdvanced)}
        className="text-midnight-400 hover:text-accent-cyan text-sm font-mono flex items-center gap-2"
      >
        <span className="text-accent-cyan">{showAdvanced ? '[-]' : '[+]'}</span>
        {t('taskForm.advancedOptions')}
      </button>

      {/* Advanced options */}
      {showAdvanced && (
        <div className="space-y-4 p-4 bg-midnight-900/50 rounded-lg border border-midnight-800">
          {/* Repository */}
          <div>
            <label className="flex items-center gap-2 text-sm text-midnight-300 font-mono mb-2">
              <GitBranch className="w-4 h-4 text-accent-lime" />
              {t('taskForm.repository')}
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
              {t('taskForm.additionalContext')}
            </label>
            <textarea
              value={context}
              onChange={(e) => setContext(e.target.value)}
              placeholder={t('taskForm.contextPlaceholder')}
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
