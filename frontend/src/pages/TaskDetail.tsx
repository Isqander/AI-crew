import { useParams, Link } from 'react-router-dom'
import { ArrowLeft, ExternalLink, Copy, Check, Network, ChevronDown, ChevronUp } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Chat } from '../components/Chat'
import { ProgressTracker } from '../components/ProgressTracker'
import { ClarificationPanel } from '../components/ClarificationPanel'
import { GraphVisualization } from '../components/GraphVisualization'
import { useTask } from '../hooks/useTask'
import { ErrorBanner } from '../components/ErrorBanner'
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
  const [showGraph, setShowGraph] = useState(true)
  const { t } = useTranslation()

  const state = threadState?.values
  const currentAgent = (state?.current_agent || 'pm') as AgentName
  const needsClarification = state?.needs_clarification || false
  const clarificationQuestion = state?.clarification_question
  const clarificationContext = state?.clarification_context

  const stageDetails: Record<string, string> = {}
  if (state?.requirements?.length) stageDetails.analyst = t('taskDetail.requirementsCount', { count: state.requirements.length })
  if (state?.architecture && Object.keys(state.architecture).length > 0) stageDetails.architect = t('taskDetail.architectureDefined')
  if (state?.code_files?.length) stageDetails.developer = t('taskDetail.filesCount', { count: state.code_files.length })
  if (state?.issues_found?.length) stageDetails.qa = t('taskDetail.issuesCount', { count: state.issues_found.length })
  if (state?.pr_url) stageDetails.complete = t('taskDetail.prCreated')
  if (state?.deploy_url) stageDetails.complete = `Deploy: ${state.deploy_url}`

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
              {state?.task ? state.task.slice(0, 50) + (state.task.length > 50 ? '...' : '') : t('common.loading')}
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
              {t('taskDetail.graph')}
              {showGraph ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
            </button>
          )}

          {state?.deploy_url && (
            <a
              href={state.deploy_url}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-2 bg-accent-cyan/10 text-accent-cyan px-4 py-2 rounded-lg
                         font-mono text-sm hover:bg-accent-cyan/20 transition-colors"
            >
              <ExternalLink className="w-4 h-4" />
              Deploy
            </a>
          )}

          {state?.pr_url && (
            <a
              href={state.pr_url}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-2 bg-accent-lime/10 text-accent-lime px-4 py-2 rounded-lg
                         font-mono text-sm hover:bg-accent-lime/20 transition-colors"
            >
              <ExternalLink className="w-4 h-4" />
              {t('taskDetail.openPR')}
            </a>
          )}
        </div>
      </div>

      {showGraph && graphId && (
        <div className="mb-6">
          <GraphVisualization graphId={graphId} currentAgent={currentAgent} />
        </div>
      )}

      {(error || runError) && (
        <ErrorBanner
          title={t('taskDetail.executionError')}
          message={runError || error?.message || t('taskDetail.unknownError')}
          badge={currentAgent && currentAgent !== 'complete' ? t('taskDetail.node', { name: currentAgent }) : undefined}
          className="mb-6"
        />
      )}

      {/* Main content */}
      <div className="grid lg:grid-cols-3 gap-6">
        {/* Left column - Chat */}
        <div className="lg:col-span-2 space-y-6">
          {needsClarification && clarificationQuestion && (
            <ClarificationPanel
              question={clarificationQuestion}
              context={clarificationContext}
              onSubmit={sendClarification}
              isLoading={isLoading}
            />
          )}
          
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
          <ProgressTracker
            currentAgent={currentAgent}
            stageDetails={stageDetails}
            error={runError || state?.error || error?.message}
          />

          {state?.tech_stack && state.tech_stack.length > 0 && (
            <div className="bg-midnight-900 rounded-lg border border-midnight-800 p-4">
              <h3 className="text-sm font-mono text-midnight-300 mb-3 uppercase tracking-wider">
                {t('taskDetail.techStack')}
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

          {state?.code_files && state.code_files.length > 0 && (
            <div className="bg-midnight-900 rounded-lg border border-midnight-800 p-4">
              <h3 className="text-sm font-mono text-midnight-300 mb-3 uppercase tracking-wider">
                {t('taskDetail.files', { count: state.code_files.length })}
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

          {state?.summary && (
            <div className="bg-midnight-900 rounded-lg border border-midnight-800 p-4">
              <h3 className="text-sm font-mono text-midnight-300 mb-3 uppercase tracking-wider">
                {t('taskDetail.summary')}
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
