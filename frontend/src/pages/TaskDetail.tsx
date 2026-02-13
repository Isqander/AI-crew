import { useParams, Link } from 'react-router-dom'
import { ArrowLeft, ExternalLink, Copy, Check, AlertCircle, Network, ChevronDown, ChevronUp } from 'lucide-react'
import { useState } from 'react'
import { Chat } from '../components/Chat'
import { ProgressTracker } from '../components/ProgressTracker'
import { ClarificationPanel } from '../components/ClarificationPanel'
import { GraphVisualization } from '../components/GraphVisualization'
import { useTask } from '../hooks/useTask'
import type { AgentName } from '../types'

export function TaskDetail() {
  const { threadId } = useParams<{ threadId: string }>()
  const {
    thread,
    threadState,
    messages,
    isLoading,
    error,
    runError,
    sendClarification
  } = useTask(threadId)
  
  const [copied, setCopied] = useState(false)
  const [showGraph, setShowGraph] = useState(false)

  const state = threadState?.values
  const currentAgent = (state?.current_agent || 'pm') as AgentName
  const needsClarification = state?.needs_clarification || false
  const clarificationQuestion = state?.clarification_question
  const clarificationContext = state?.clarification_context

  // Get graph_id from thread metadata (set by /api/run → _create_thread)
  const graphId = (thread?.metadata as Record<string, unknown>)?.graph_id as string | undefined

  const handleCopy = () => {
    if (threadId) {
      navigator.clipboard.writeText(threadId)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }
  }

  return (
    <div className="max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-4">
          <Link 
            to="/"
            className="text-midnight-400 hover:text-accent-cyan transition-colors"
          >
            <ArrowLeft className="w-5 h-5" />
          </Link>
          <div>
            <h1 className="text-xl font-mono font-semibold text-midnight-100">
              {state?.task ? state.task.slice(0, 50) + (state.task.length > 50 ? '...' : '') : 'Загрузка...'}
            </h1>
            <div className="flex items-center gap-2 mt-1">
              <code className="text-xs text-midnight-500 font-mono">
                {threadId?.slice(0, 8)}...
              </code>
              <button 
                onClick={handleCopy}
                className="text-midnight-500 hover:text-accent-cyan transition-colors"
              >
                {copied ? <Check className="w-3 h-3" /> : <Copy className="w-3 h-3" />}
              </button>
              {graphId && (
                <span className="ml-2 px-2 py-0.5 bg-accent-cyan/10 text-accent-cyan text-xs font-mono rounded-full">
                  {graphId}
                </span>
              )}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {/* Graph Visualization Toggle */}
          {graphId && (
            <button
              onClick={() => setShowGraph(!showGraph)}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg font-mono text-sm transition-colors border
                ${showGraph
                  ? 'bg-accent-cyan/20 text-accent-cyan border-accent-cyan/40'
                  : 'bg-midnight-900 text-midnight-300 border-midnight-700 hover:border-accent-cyan/30 hover:text-accent-cyan'
                }`}
            >
              <Network className="w-4 h-4" />
              Граф
              {showGraph ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
            </button>
          )}

          {/* PR Link */}
          {state?.pr_url && (
            <a
              href={state.pr_url}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-2 bg-accent-lime/10 text-accent-lime px-4 py-2 rounded-lg
                         font-mono text-sm hover:bg-accent-lime/20 transition-colors"
            >
              <ExternalLink className="w-4 h-4" />
              Открыть PR
            </a>
          )}
        </div>
      </div>

      {/* Graph Visualization (collapsible) */}
      {showGraph && graphId && (
        <div className="mb-6">
          <GraphVisualization graphId={graphId} currentAgent={currentAgent} />
        </div>
      )}

      {/* Error banner */}
      {(error || runError) && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-4 mb-6">
          <div className="flex items-center gap-2 text-red-400 font-mono text-sm">
            <AlertCircle className="w-5 h-5" />
            <span className="font-semibold">Ошибка выполнения</span>
          </div>
          <p className="text-red-300/80 text-sm font-mono mt-2">
            {runError || error?.message}
          </p>
        </div>
      )}

      {/* Main content */}
      <div className="grid lg:grid-cols-3 gap-6">
        {/* Left column - Chat */}
        <div className="lg:col-span-2 space-y-6">
          {/* Clarification panel */}
          {needsClarification && clarificationQuestion && (
            <ClarificationPanel
              question={clarificationQuestion}
              context={clarificationContext}
              onSubmit={sendClarification}
              isLoading={isLoading}
            />
          )}
          
          {/* Chat */}
          <div className="h-[600px]">
            <Chat
              messages={messages}
              currentAgent={currentAgent}
              needsClarification={needsClarification}
              clarificationQuestion={clarificationQuestion}
              onSendMessage={needsClarification ? sendClarification : undefined}
              isLoading={isLoading}
            />
          </div>
        </div>

        {/* Right column - Progress & Details */}
        <div className="space-y-6">
          {/* Progress tracker */}
          <ProgressTracker
            currentAgent={currentAgent}
            requirements={state?.requirements || []}
            architecture={state?.architecture || {}}
            codeFiles={state?.code_files || []}
            issuesFound={state?.issues_found || []}
            prUrl={state?.pr_url}
            error={runError || state?.error || error?.message}
          />

          {/* Tech stack */}
          {state?.tech_stack && state.tech_stack.length > 0 && (
            <div className="bg-midnight-900 rounded-lg border border-midnight-800 p-4">
              <h3 className="text-sm font-mono text-midnight-300 mb-3 uppercase tracking-wider">
                Технологии
              </h3>
              <div className="flex flex-wrap gap-2">
                {state.tech_stack.map((tech, idx) => (
                  <span
                    key={idx}
                    className="bg-accent-cyan/10 text-accent-cyan px-3 py-1 rounded-full font-mono text-xs"
                  >
                    {tech}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Code files */}
          {state?.code_files && state.code_files.length > 0 && (
            <div className="bg-midnight-900 rounded-lg border border-midnight-800 p-4">
              <h3 className="text-sm font-mono text-midnight-300 mb-3 uppercase tracking-wider">
                Файлы ({state.code_files.length})
              </h3>
              <div className="space-y-1 max-h-[200px] overflow-y-auto">
                {state.code_files.map((file, idx) => (
                  <div
                    key={idx}
                    className="text-xs font-mono text-midnight-400 flex items-center gap-2"
                  >
                    <span className="text-accent-lime">📄</span>
                    {file.path}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Summary */}
          {state?.summary && (
            <div className="bg-midnight-900 rounded-lg border border-midnight-800 p-4">
              <h3 className="text-sm font-mono text-midnight-300 mb-3 uppercase tracking-wider">
                Итог
              </h3>
              <p className="text-sm text-midnight-200 font-mono whitespace-pre-wrap">
                {state.summary}
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
